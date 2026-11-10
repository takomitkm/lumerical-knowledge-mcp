"""rag-shim: hybrid retrieval API (Qdrant vectors + tantivy BM25 -> RRF -> SiliconFlow rerank).
Runs on 102 as a user-level systemd service. Env from ~/.config/rag/rag.env.
"""
import os
import json
import uuid
import threading
from typing import Any, Dict, Optional, List

import httpx
import tantivy
from fastapi import FastAPI, Header, HTTPException, Body

SF_BASE = os.environ.get("SILICONFLOW_BASE", "https://api.siliconflow.cn/v1").rstrip("/")
SF_KEY = os.environ["SILICONFLOW_API_KEY"]
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
RERANK_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
RAG_TOKEN = os.environ["RAG_TOKEN"]
BM25_DIR = os.environ.get("BM25_DIR", os.path.expanduser("~/rag/storage/bm25"))
DEFAULT_COLLECTION = os.environ.get("DEFAULT_COLLECTION", "lumerical")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
RRF_K = int(os.environ.get("RRF_K", "60"))

app = FastAPI(title="rag-shim", version="1.0")
_lock = threading.Lock()
_index = None
_writer = None

# ---------- helpers ----------
def _bm25():
    global _index, _writer
    if _writer is None:
        with _lock:
            if _writer is None:
                os.makedirs(BM25_DIR, exist_ok=True)
                b = tantivy.SchemaBuilder()
                b.add_text_field("cid", stored=True)
                b.add_text_field("collection", stored=True)
                b.add_text_field("text", stored=True)
                b.add_text_field("meta", stored=True)
                _index = tantivy.Index(b.build(), path=BM25_DIR)
                _writer = _index.writer()
    return _index, _writer


def _auth(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    if authorization[7:].strip() != RAG_TOKEN:
        raise HTTPException(403, "bad token")


def _sf_embed(texts: List[str]) -> List[List[float]]:
    r = httpx.post(
        f"{SF_BASE}/embeddings",
        headers={"Authorization": f"Bearer {SF_KEY}"},
        json={"model": EMBED_MODEL, "input": texts, "encoding_format": "float"},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()["data"]
    data.sort(key=lambda x: x["index"])
    return [d["embedding"] for d in data]


def _sf_rerank(query: str, docs: List[str], top_n: int):
    if not docs:
        return []
    r = httpx.post(
        f"{SF_BASE}/rerank",
        headers={"Authorization": f"Bearer {SF_KEY}"},
        json={"model": RERANK_MODEL, "query": query, "documents": docs,
              "top_n": top_n, "return_documents": False},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["results"]


def _qd(method: str, path: str, **kw):
    return httpx.request(method, f"{QDRANT_URL}{path}", timeout=60, **kw)


def _ensure_collection(name: str):
    r = _qd("GET", f"/collections/{name}")
    if r.status_code == 200:
        return
    # NOTE: Qdrant 1.20 int8 scalar quantization uses AVX SIMD -> SIGILL on this old
    # Celeron G1610 (no AVX). So: NO quantization, and indexing_threshold huge so HNSW
    # is never built (distance SIMD avoided); brute-force search is fine for ~13k vectors.
    body = {
        "vectors": {"size": EMBED_DIM, "distance": "Cosine"},
        "optimizers_config": {"indexing_threshold": 1000000},
    }
    _qd("PUT", f"/collections/{name}", json=body).raise_for_status()


def _pid(collection: str, cid: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection}:{cid}"))


def _fetch_doc_by_doc_id(doc_id: str, collection: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Reassemble one logical document by meta.doc_id (compat recipe retrieval).

    Stable-ID lookup only: callers never pass file paths.
    """
    must = [{"key": "meta.doc_id", "match": {"value": doc_id}}]
    if collection:
        cols = [collection]
    else:
        try:
            cols = [c["name"] for c in _qd("GET", "/collections").json()["result"]["collections"]]
        except Exception:  # noqa: BLE001
            cols = [DEFAULT_COLLECTION]
    for col in cols:
        body = {"filter": {"must": must}, "limit": 500, "with_payload": True, "with_vector": False}
        r = _qd("POST", "/collections/%s/points/scroll" % col, json=body)
        if r.status_code != 200:
            continue
        pts = r.json()["result"].get("points", [])
        if pts:
            pts.sort(key=lambda p: ((p["payload"].get("meta") or {}).get("chunk_idx") or 0))
            return {"collection": col, "count": len(pts),
                    "text": "\n\n".join(p["payload"].get("text", "") for p in pts)}
    return None


# ---------- endpoints ----------
@app.get("/health")
def health():
    out: Dict[str, Any] = {"shim": "ok"}
    try:
        out["qdrant"] = httpx.get(f"{QDRANT_URL}/healthz", timeout=5).text
    except Exception as e:  # noqa: BLE001
        out["qdrant"] = f"ERR {e}"
    try:
        idx, _ = _bm25()
        out["bm25_docs"] = idx.searcher().num_docs
    except Exception as e:  # noqa: BLE001
        out["bm25_docs"] = f"ERR {e}"
    return out


@app.post("/ingest")
def ingest(payload: Dict[str, Any] = Body(...), authorization: Optional[str] = Header(None)):
    _auth(authorization)
    collection = payload.get("collection") or DEFAULT_COLLECTION
    chunks = payload.get("chunks") or []
    if not chunks:
        return {"ok": True, "inserted": 0, "collection": collection}
    _ensure_collection(collection)
    index, writer = _bm25()
    inserted = 0
    B = 32
    for i in range(0, len(chunks), B):
        batch = chunks[i:i + B]
        vecs = _sf_embed([c["text"] for c in batch])
        pts = []
        for c, v in zip(batch, vecs):
            cid = str(c["id"])
            pts.append({
                "id": _pid(collection, cid),
                "vector": v,
                "payload": {"cid": cid, "collection": collection,
                            "text": c["text"], "meta": c.get("meta") or {}},
            })
        _qd("PUT", f"/collections/{collection}/points?wait=true", json={"points": pts}).raise_for_status()
        with _lock:
            for c in batch:
                d = tantivy.Document()
                d.add_text("cid", str(c["id"]))
                d.add_text("collection", collection)
                d.add_text("text", c["text"])
                d.add_text("meta", json.dumps(c.get("meta") or {}, ensure_ascii=False))
                writer.add_document(d)
            writer.commit()
            index.reload()
        inserted += len(batch)
    return {"ok": True, "inserted": inserted, "collection": collection}


@app.get("/search")
def search(q: str, top_k: int = 8, collection: Optional[str] = None,
           doc_type: Optional[str] = None, version: Optional[str] = None,
           authorization: Optional[str] = Header(None)):
    _auth(authorization)
    collection = collection or DEFAULT_COLLECTION
    q = (q or "").strip()
    if not q:
        raise HTTPException(400, "empty q")

    def _keep(m: Dict[str, Any]) -> bool:
        if doc_type and (m or {}).get("doc_type") != doc_type:
            return False
        if version and (m or {}).get("version") != version:
            return False
        return True

    qv = _sf_embed([q])[0]

    # vector branch
    vec_hits: List[Dict[str, Any]] = []
    r = _qd("POST", f"/collections/{collection}/points/search",
            json={"vector": qv, "limit": 50, "with_payload": True})
    if r.status_code == 200:
        for h in r.json()["result"]:
            pl = h["payload"]
            m = pl.get("meta") or {}
            if not _keep(m):
                continue
            vec_hits.append({"cid": pl.get("cid"), "text": pl.get("text", ""),
                             "meta": m, "vscore": h["score"]})

    # bm25 branch
    bm_hits: List[Dict[str, Any]] = []
    try:
        index, _ = _bm25()
        index.reload()
        searcher = index.searcher()
        try:
            query = index.parse_query(q, ["text"])
        except Exception:  # noqa: BLE001
            query = index.parse_query(q.replace(":", " ").replace('"', " "), ["text"])
        for score, addr in searcher.search(query, 50).hits:
            d = searcher.doc(addr)
            col = d.get_first("collection") or ""
            if collection and col != collection:
                continue
            m = json.loads(d.get_first("meta") or "{}")
            if not _keep(m):
                continue
            bm_hits.append({"cid": d.get_first("cid"), "text": d.get_first("text") or "",
                            "meta": m, "bscore": score})
    except Exception:  # noqa: BLE001
        bm_hits = []

    # reciprocal rank fusion
    scores: Dict[str, float] = {}
    cand: Dict[str, Dict[str, Any]] = {}
    for rank, h in enumerate(vec_hits):
        k = h["cid"]
        if k is None:
            continue
        scores[k] = scores.get(k, 0.0) + 1.0 / (RRF_K + rank + 1)
        cand.setdefault(k, h)
    for rank, h in enumerate(bm_hits):
        k = h["cid"]
        if k is None:
            continue
        scores[k] = scores.get(k, 0.0) + 1.0 / (RRF_K + rank + 1)
        if k not in cand:
            cand[k] = h
        else:
            cand[k]["bscore"] = h.get("bscore")

    fused = sorted(scores.items(), key=lambda x: -x[1])[:20]
    cands = [cand[k] for k, _ in fused]

    # rerank: feed breadcrumb + doc-type tag ahead of the body so the cross-encoder can
    # tell an API/command page from an application example (no re-index needed).
    def _rerank_doc(c: Dict[str, Any]) -> str:
        m = c.get("meta") or {}
        head = m.get("breadcrumb") or " > ".join(
            x for x in [m.get("category"), m.get("section"), m.get("title")] if x)
        tag = " (example script)" if m.get("doc_type") == "example" else ""
        if m.get("doc_type") == "kb_article" and m.get("title"):
            tag += " (reference)"
        return (head + tag + "\n" + c.get("text", "")) if head else c.get("text", "")

    try:
        rr = _sf_rerank(q, [_rerank_doc(c) for c in cands], max(top_k, 1))
        for item in rr:
            cands[item["index"]]["rerank"] = item["relevance_score"]
        final = [cands[item["index"]] for item in rr]
    except Exception:  # noqa: BLE001
        final = cands[:top_k]

    return {
        "query": q, "collection": collection, "count": len(final[:top_k]),
        "results": [{
            "cid": c.get("cid"), "text": c.get("text", ""), "meta": c.get("meta") or {},
            "score": c.get("rerank"), "rrf": round(scores.get(c["cid"], 0.0), 6),
            "vscore": c.get("vscore"), "bscore": c.get("bscore"),
        } for c in final[:top_k]],
    }


@app.get("/collections")
def list_collections(authorization: Optional[str] = Header(None)):
    _auth(authorization)
    out = []
    try:
        r = _qd("GET", "/collections")
        for c in r.json()["result"]["collections"]:
            n = c["name"]
            info = _qd("GET", "/collections/%s" % n)
            cnt = info.json()["result"].get("points_count") if info.status_code == 200 else None
            out.append({"name": n, "points": cnt})
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    return {"collections": out}


@app.get("/document")
def get_document(url: str, collection: Optional[str] = None, limit: int = 300,
                 authorization: Optional[str] = Header(None)):
    """Return every chunk of one document (by URL), reassembled in order."""
    _auth(authorization)
    must = [{"key": "meta.url", "match": {"value": url}}]
    if collection:
        cols = [collection]
    else:
        try:
            cols = [c["name"] for c in _qd("GET", "/collections").json()["result"]["collections"]]
        except Exception:  # noqa: BLE001
            cols = [DEFAULT_COLLECTION]
    pts = []
    for col in cols:
        body = {"filter": {"must": must}, "limit": int(limit),
                "with_payload": True, "with_vector": False}
        r = _qd("POST", "/collections/%s/points/scroll" % col, json=body)
        if r.status_code == 200:
            pts += r.json()["result"].get("points", [])
    if not pts:
        raise HTTPException(404, "url not found: %s" % url)
    pts.sort(key=lambda p: ((p["payload"].get("meta") or {}).get("chunk_idx") or 0))
    metas = [(p["payload"].get("meta") or {}) for p in pts]
    text = "\n\n".join(p["payload"].get("text", "") for p in pts)
    return {"url": url, "count": len(pts), "chars": len(text),
            "meta": metas[0] if metas else {}, "text": text}


@app.post("/admin/rebuild-bm25")
def rebuild(collection: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Rebuild the single tantivy index from ALL collections in Qdrant.

    (The BM25 index is shared by every collection: docs carry a `collection` field and
    search filters on it. Rebuilding only one collection would silently wipe the others.)
    """
    _auth(authorization)
    index, writer = _bm25()
    with _lock:
        writer.delete_all_documents()
        writer.commit()
        index.reload()

    cols: List[str] = []
    try:
        r = _qd("GET", "/collections")
        if r.status_code == 200:
            cols = [c["name"] for c in r.json()["result"]["collections"]]
    except Exception:  # noqa: BLE001
        cols = []
    if not cols:
        cols = [collection or DEFAULT_COLLECTION]

    total = 0
    for col in cols:
        offset = None
        while True:
            body: Dict[str, Any] = {"limit": 256, "with_payload": True, "with_vector": False}
            if offset is not None:
                body["offset"] = offset
            r = _qd("POST", f"/collections/{col}/points/scroll", json=body)
            if r.status_code != 200:
                break
            res = r.json()["result"]
            pts = res.get("points", [])
            if pts:
                with _lock:
                    for p in pts:
                        pl = p["payload"]
                        d = tantivy.Document()
                        d.add_text("cid", pl.get("cid", ""))
                        d.add_text("collection", pl.get("collection", col))
                        d.add_text("text", pl.get("text", ""))
                        d.add_text("meta", json.dumps(pl.get("meta") or {}, ensure_ascii=False))
                        writer.add_document(d)
                    writer.commit()
                    index.reload()
            total += len(pts)
            offset = res.get("next_page_offset")
            if offset is None:
                break
    return {"ok": True, "indexed": total, "collections": cols}


# ---------- compatibility layer wiring (reuses the auth + document path above) ----------
from compat import api as compat_api  # noqa: E402

compat_api.bind_auth(_auth)
compat_api.bind_doc_fetcher(_fetch_doc_by_doc_id)
app.include_router(compat_api.router)

"""Ingest corpus/chunks.jsonl into rag-shim on 102. Batched, resumable, then rebuild BM25.
Env: RAG_TOKEN (required), RAG_BASE (default http://RAG_HOST:8900), COLLECTION=lumerical, BATCH=48
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = os.path.dirname(__file__)
CHUNKS = os.environ.get("CHUNKS", os.path.join(BASE, "corpus", "chunks.jsonl"))
SHIM = os.environ.get("RAG_BASE", "http://RAG_HOST:8900").rstrip("/")
TOKEN = os.environ["RAG_TOKEN"]
COLLECTION = os.environ.get("COLLECTION", "lumerical")
BATCH = int(os.environ.get("BATCH", "48"))
SENT = os.environ.get("SENT", os.path.join(BASE, "corpus", "sent_ids.txt"))
FAILED = os.environ.get("FAILED", os.path.join(BASE, "corpus", "failed_batches.jsonl"))


def _req(method, path, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        SHIM + path, data=data, method=method,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def post_batch(batch):
    last = None
    for attempt in range(6):
        try:
            return _req("POST", "/ingest", {"collection": COLLECTION, "chunks": batch})
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            last = "HTTP %s: %s" % (e.code, msg)
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(last)
        except Exception as e:  # noqa: BLE001
            last = str(e)
            if attempt < 5:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(last)
    raise RuntimeError(last)


def main():
    rows = []
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    sent = set()
    if os.path.exists(SENT):
        with open(SENT, encoding="utf-8") as f:
            sent = set(x.strip() for x in f if x.strip())
    pending = [r for r in rows if r["id"] not in sent]
    print("total=%d already_sent=%d pending=%d" % (len(rows), len(sent), len(pending)))

    nbatches = (len(pending) + BATCH - 1) // BATCH
    ok = 0
    fail = 0
    fout = open(FAILED, "a", encoding="utf-8")
    sout = open(SENT, "a", encoding="utf-8")
    t0 = time.time()
    for bi in range(nbatches):
        batch = pending[bi * BATCH:(bi + 1) * BATCH]
        try:
            res = post_batch(batch)
            for r in batch:
                sout.write(r["id"] + "\n")
            sout.flush()
            ok += len(batch)
            el = time.time() - t0
            print("[%d/%d] +%d -> inserted=%s  (ok=%d fail=%d, %.0fs)"
                  % (bi + 1, nbatches, len(batch), res.get("inserted"), ok, fail, el), flush=True)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "400" in msg:
                # embedding rejected the batch (usually one over-long input): retry one by one,
                # truncating pathological chunks so they still get indexed.
                print("[%d/%d] batch 400 -> retry as singles" % (bi + 1, nbatches), flush=True)
                for r in batch:
                    try:
                        post_batch([r])
                        sout.write(r["id"] + "\n")
                        ok += 1
                        continue
                    except Exception as e2:  # noqa: BLE001
                        if "400" in str(e2) and len(r["text"]) > 6000:
                            r2 = dict(r)
                            r2["text"] = r["text"][:6000]
                            try:
                                post_batch([r2])
                                sout.write(r["id"] + "\n")
                                ok += 1
                                print("   truncated+ok %s (was %d chars)" % (r["id"], len(r["text"])), flush=True)
                                continue
                            except Exception as e3:  # noqa: BLE001
                                e2 = e3
                        fail += 1
                        fout.write(json.dumps({"id": r["id"], "error": str(e2)}) + "\n")
                        fout.flush()
                sout.flush()
            else:
                fail += len(batch)
                fout.write(json.dumps({"batch_index": bi, "ids": [r["id"] for r in batch], "error": msg}) + "\n")
                fout.flush()
                print("[%d/%d] FAILED %d: %s" % (bi + 1, nbatches, len(batch), e), flush=True)
        time.sleep(0.15)
    fout.close()
    sout.close()
    print("INGEST_DONE ok=%d fail=%d in %.0fs" % (ok, fail, time.time() - t0))

    print(">> rebuilding BM25 from Qdrant (dedup + align)")
    try:
        print(_req("POST", "/admin/rebuild-bm25?collection=" + COLLECTION, {}, timeout=600))
    except Exception as e:  # noqa: BLE001
        print("REBUILD_FAIL", e)
    try:
        print("HEALTH", _req("GET", "/health", timeout=30))
    except Exception as e:  # noqa: BLE001
        print("HEALTH_FAIL", e)


if __name__ == "__main__":
    main()

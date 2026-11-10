"""Build chunks for the fdtdx corpus using the same structure-first chunker as the KB."""
import glob
import hashlib
import json
import os

from build_chunks import chunk_blocks, html_to_blocks

BASE = os.path.dirname(__file__)
OUTDIR = os.path.join(BASE, "corpus", "fdtdx")
MAXEX = 4000


def short(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]


def split_by_lines(t, limit):
    if len(t) <= limit:
        return [t]
    parts, cur = [], ""
    for ln in t.split("\n"):
        if cur and len(cur) + len(ln) + 1 > limit:
            parts.append(cur)
            cur = ln
        else:
            cur = ln if not cur else cur + "\n" + ln
    if cur:
        parts.append(cur)
    return parts


def main():
    arts = []
    files = sorted(glob.glob(os.path.join(OUTDIR, "articles*.json")) +
                   glob.glob(os.path.join(OUTDIR, "paper*.json")))
    for fp in files:
        block = json.load(open(fp, encoding="utf-8"))
        arts += block
        print("  +%d docs from %s" % (len(block), os.path.basename(fp)))
    out = []
    for a in arts:
        url = a.get("html_url") or ""
        sec = a.get("section") or ""
        if not sec and "/en/stable/" in url:
            tail = url.split("/en/stable/", 1)[1]
            segs = [x for x in tail.split("/") if x]
            sec = segs[0] if len(segs) > 1 else ""
        base = {
            "source": "fdtdx",
            "doc_type": "doc" if a.get("kind") != "paper" else "paper",
            "category": a.get("category"),
            "section": sec,
            "title": a.get("title"),
            "url": url,
            "doc_id": a.get("id"),
            "parser": "lxml-html",
        }
        base["breadcrumb"] = " > ".join(
            x for x in [a.get("category"), a.get("section"), a.get("title")] if x)
        for c in chunk_blocks(html_to_blocks(a.get("body")), base):
            out.append({"id": "fdtdx:%s:%s" % (short(str(a.get("id"))), c["meta"]["chunk_idx"]),
                        "text": c["text"], "meta": c["meta"]})

    exdir = os.path.join(OUTDIR, "examples")
    nex = 0
    for fp in sorted(os.listdir(exdir)) if os.path.isdir(exdir) else []:
        if not fp.endswith(".py"):
            continue
        txt = open(os.path.join(exdir, fp), encoding="utf-8", errors="replace").read()
        if not txt.strip():
            continue
        meta = {"source": "fdtdx", "doc_type": "example", "path": fp, "filename": fp,
                "parser": "raw", "breadcrumb": "fdtdx examples > " + fp}
        parts = split_by_lines(txt, MAXEX)
        if len(parts) == 1:
            out.append({"id": "fdtdx:ex:%s" % fp, "text": "#!/ fdtdx example: %s\n%s" % (fp, txt),
                        "meta": dict(meta)})
        else:
            for k, pt in enumerate(parts):
                m = dict(meta)
                m["part"] = k
                m["parts"] = len(parts)
                m["breadcrumb"] = meta["breadcrumb"] + " [part %d/%d]" % (k + 1, len(parts))
                out.append({"id": "fdtdx:ex:%s#p%d" % (fp, k),
                            "text": "#!/ fdtdx example: %s (part %d/%d)\n%s" % (fp, k + 1, len(parts), pt),
                            "meta": m})
        nex += 1

    # API reference from the installed package's docstrings (WSL venv)
    apif = os.path.join(OUTDIR, "api_filtered.json")
    napi = 0
    if os.path.isfile(apif):
        for r in json.load(open(apif, encoding="utf-8")):
            q = r.get("qualname") or ""
            kind = r.get("kind") or ""
            sig = (r.get("signature") or "").strip()
            doc = (r.get("doc") or "").strip()[:3000]
            parts = q.split(".")
            module = ".".join(parts[:-1]) if len(parts) > 1 else "fdtdx"
            text = "%s\n%s%s\n\n%s" % (q, kind, (" " + sig) if sig else "", doc)
            meta = {"source": "fdtdx", "doc_type": "api", "category": "fdtdx API",
                    "section": module, "title": parts[-1], "qualname": q,
                    "parser": "python-docstring",
                    "breadcrumb": "fdtdx API > %s > %s" % (module, parts[-1])}
            out.append({"id": "fdtdx:api:%s" % hashlib.md5(q.encode("utf-8")).hexdigest()[:16],
                        "text": text.strip(), "meta": meta})
            napi += 1

    with open(os.path.join(OUTDIR, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    docs = sum(1 for c in out if c["meta"]["doc_type"] == "doc")
    exs = sum(1 for c in out if c["meta"]["doc_type"] == "example")
    napi_all = sum(1 for c in out if c["meta"]["doc_type"] == "api")
    print("fdtdx articles=%d examples_files=%d  chunks: doc=%d example=%d api=%d TOTAL=%d"
          % (len(arts), nex, docs, exs, napi_all, len(out)))
    if out:
        print("avg_chars=%d max_chars=%d" % (sum(len(c["text"]) for c in out) // len(out),
                                             max(len(c["text"]) for c in out)))


if __name__ == "__main__":
    main()



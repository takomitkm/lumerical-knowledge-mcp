"""Build the `lumerical_v241` collection from the authoritative on-disk docs.json
(school install: C:\\Program Files\\Lumerical\\v241\\api\\python\\docs.json).

One chunk per script command (split at line boundaries if a doc exceeds ~3500 chars).
"""
import json
import os

BASE = os.path.dirname(__file__)
SRC = os.path.join(BASE, "corpus", "lumerical_v241", "docs.json")
OUT = os.path.join(BASE, "corpus", "lumerical_v241", "chunks.jsonl")
MAXC = 3500


def split_lines(t, limit):
    if len(t) <= limit:
        return [t]
    parts, cur = [], []
    n = 0
    for ln in t.split("\n"):
        if cur and n + len(ln) + 1 > limit:
            parts.append("\n".join(cur))
            cur, n = [], 0
        cur.append(ln)
        n += len(ln) + 1
    if cur:
        parts.append("\n".join(cur))
    return parts


def main():
    docs = json.load(open(SRC, encoding="utf-8"))
    out = []
    for name, d in sorted(docs.items()):
        text = (d.get("text") or "").strip()
        link = (d.get("link") or "").strip()
        if not text:
            continue
        head = "%s\n%s\n" % (name, link)
        parts = split_lines(text, MAXC)
        for k, pt in enumerate(parts):
            meta = {
                "source": "lumerical-v241",
                "doc_type": "command",
                "version": "v241",
                "title": name,
                "url": link,
                "command": name,
                "parser": "docs.json",
                "breadcrumb": "Lumerical v241 script commands > %s" % name,
            }
            if len(parts) > 1:
                meta["part"] = k
                meta["parts"] = len(parts)
                meta["breadcrumb"] += " [part %d/%d]" % (k + 1, len(parts))
            body = head + ("[part %d/%d]\n" % (k + 1, len(parts)) if len(parts) > 1 else "") + pt
            out.append({"id": "v241:%s%s" % (name, "" if len(parts) == 1 else "#p%d" % k), "text": body, "meta": meta})

    with open(OUT, "w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print("commands=%d chunks=%d max_chars=%d" % (len(docs), len(out), max(len(c["text"]) for c in out)))


if __name__ == "__main__":
    main()

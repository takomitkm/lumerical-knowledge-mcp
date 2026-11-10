"""Build chunks from (a) crawled Zendesk KB HTML articles and (b) Lumerical .lsf examples.

Structure-first chunking (per PLAN Phase 3):
 1. heading-level boundaries start new chunks
 2. code blocks are never split
 3. only split a section when it exceeds ~MAXTOK tokens, at paragraph boundaries
 4. every chunk carries breadcrumb metadata -> Qdrant payload
Output: corpus/chunks.jsonl  (one JSON object per line: {id,text,meta})
"""
import json
import os
import glob
import re

from lxml import html as LH

BASE = os.path.dirname(__file__)
CORPUS = os.path.join(BASE, "corpus")
ZEN = os.path.join(CORPUS, "zendesk")
MAXTOK = 1024
TINY_MERGE = 200       # chunks shorter than this get merged into a neighbour
TABLE_SPLIT = 4000     # chars: split oversized tables by rows (header repeated)
CODE_SPLIT = 6000      # chars: split oversized code blocks at LINE boundaries
PARA_SPLIT = 4000      # chars: split an oversized single paragraph at sentence boundaries

SENT_RE = re.compile(r"(?<=[.!?。！？])\s+")


def split_para(tx, limit):
    if len(tx) <= limit:
        return [tx]
    parts, cur = [], ""
    for seg in SENT_RE.split(tx):
        if cur and len(cur) + len(seg) + 1 > limit:
            parts.append(cur)
            cur = seg
        else:
            cur = seg if not cur else cur + " " + seg
    if cur:
        parts.append(cur)
    out = []
    for p in parts:
        while len(p) > limit * 2:
            out.append(p[:limit])
            p = p[limit:]
        out.append(p)
    return out


def norm(s):
    return " ".join((s or "").split())


def est_tok(s):
    return max(1, len(s) // 4)


def html_to_blocks(body):
    if not body:
        return []
    try:
        root = LH.fromstring("<div id='__w'>" + body + "</div>")
    except Exception:  # noqa: BLE001
        return [{"type": "para", "text": norm(body), "hpath": []}]
    wrapper = root.get_element_by_id("__w")
    out = []
    stack = {}  # level -> heading text

    def path():
        return [stack[k] for k in sorted(stack)]

    def walk(el):
        for ch in el:
            if not isinstance(ch.tag, str):
                continue  # skip comments / PIs
            t = ch.tag.lower()
            if t in ("h1", "h2", "h3", "h4", "h5", "h6"):
                lvl = int(t[1])
                txt = norm(ch.text_content())
                if not txt:
                    continue
                for k in list(stack):
                    if k >= lvl:
                        del stack[k]
                stack[lvl] = txt
                out.append({"type": "heading", "level": lvl, "text": txt, "hpath": path()})
            elif t == "pre":
                code = (ch.text_content() or "").strip("\n")
                if code and code.strip():
                    if len(code) <= CODE_SPLIT:
                        out.append({"type": "code", "text": code, "hpath": path()})
                    else:  # split at line boundaries, never mid-line
                        lines = code.split("\n")
                        parts, cur, curlen = [], [], 0
                        for ln in lines:
                            if cur and curlen + len(ln) + 1 > CODE_SPLIT:
                                parts.append("\n".join(cur))
                                cur, curlen = [], 0
                            cur.append(ln)
                            curlen += len(ln) + 1
                        if cur:
                            parts.append("\n".join(cur))
                        for k, pt in enumerate(parts):
                            out.append({"type": "code",
                                        "text": "[code part %d/%d]\n%s" % (k + 1, len(parts), pt),
                                        "hpath": path()})
            elif t == "table":
                rows = []
                for tr in ch.xpath(".//tr"):
                    cells = [norm(td.text_content()) for td in tr.xpath("./td|./th")]
                    if any(cells):
                        rows.append(" | ".join(cells))
                if not rows:
                    continue
                whole = "\n".join(rows)
                if len(whole) <= TABLE_SPLIT or len(rows) < 2:
                    out.append({"type": "table", "text": whole, "hpath": path()})
                else:  # split by rows, repeat the header row in every part
                    header, body = rows[0], rows[1:]
                    parts, cur, curlen = [], [], 0
                    for r in body:
                        if cur and curlen + len(r) + 1 > TABLE_SPLIT:
                            parts.append(cur)
                            cur, curlen = [], 0
                        cur.append(r)
                        curlen += len(r) + 1
                    if cur:
                        parts.append(cur)
                    for k, pt in enumerate(parts):
                        out.append({"type": "table",
                                    "text": header + "\n" + "\n".join(pt) +
                                            "\n[table part %d/%d]" % (k + 1, len(parts)),
                                    "hpath": path()})
            elif t in ("ul", "ol"):
                bullets = []
                for li in ch.xpath("./li"):
                    tx = norm(li.text_content())
                    if not tx:
                        continue
                    for k, pt in enumerate(split_para(tx, PARA_SPLIT)):
                        bullets.append("\u2022 " + pt if k == 0 else "  " + pt)
                if bullets:
                    cur, curlen = [], 0
                    for b in bullets:
                        if cur and curlen + len(b) + 1 > PARA_SPLIT:
                            out.append({"type": "list", "text": "\n".join(cur), "hpath": path()})
                            cur, curlen = [], 0
                        cur.append(b)
                        curlen += len(b) + 1
                    if cur:
                        out.append({"type": "list", "text": "\n".join(cur), "hpath": path()})
            elif t == "p":
                tx = norm(ch.text_content())
                if tx:
                    for pt in split_para(tx, PARA_SPLIT):
                        out.append({"type": "para", "text": pt, "hpath": path()})
            elif t in ("div", "section", "article", "span", "body", "tbody", "thead",
                       "blockquote", "figure", "dl", "dd", "dt", "center", "details", "summary"):
                walk(ch)
            else:
                if len(ch) == 0:
                    tx = norm(ch.text_content())
                    if tx:
                        out.append({"type": "para", "text": tx, "hpath": path()})
                else:
                    walk(ch)

    walk(wrapper)
    return out


def render(blocks):
    lines = []
    for b in blocks:
        if b["type"] == "heading":
            lines.append("#" * b["level"] + " " + b["text"])
        elif b["type"] == "code":
            lines.append("```\n" + b["text"].strip("\n") + "\n```")
        else:
            lines.append(b["text"])
    return "\n\n".join(lines)


def chunk_blocks(blocks, base):
    """Structure-first chunking shared by every corpus (zendesk KB, fdtdx docs)."""
    if not blocks:
        return []
    chunks = []
    cur = []
    cur_tok = 0

    def flush():
        nonlocal cur, cur_tok
        if not cur:
            return
        text = render(cur)
        if text.strip() and (len(text.strip()) >= 80 or "```" in text):
            m = dict(base)
            m["chunk_idx"] = len(chunks)
            chunks.append({"text": text, "meta": m})
        cur = []
        cur_tok = 0

    for b in blocks:
        bt = est_tok(b["text"])
        if b["type"] == "heading":
            if cur:
                flush()
            cur.append(b)
            cur_tok += bt
            continue
        if b["type"] == "code":
            if cur and cur_tok + bt > MAXTOK:
                flush()
            cur.append(b)
            cur_tok += bt
            continue
        if cur and cur_tok + bt > MAXTOK:
            flush()
        cur.append(b)
        cur_tok += bt
    flush()

    # merge tiny chunks into a neighbour (same article) to cut lonely-heading noise
    if chunks:
        merged = []
        carry = None
        for c in chunks:
            if carry is not None:
                c = {"text": carry + "\n\n" + c["text"], "meta": c["meta"]}
                carry = None
            if len(c["text"].strip()) < TINY_MERGE:
                if merged:
                    merged[-1]["text"] = merged[-1]["text"] + "\n\n" + c["text"]
                else:
                    carry = c["text"]
            else:
                merged.append(c)
        if carry:
            if merged:
                merged[-1]["text"] = merged[-1]["text"] + "\n\n" + carry
            else:
                merged.append({"text": carry, "meta": dict(base)})
        chunks = merged
    for i, c in enumerate(chunks):
        c["meta"]["chunk_idx"] = i
    return chunks


def chunk_article(article, section_name, category_name):
    base = {
        "source": "ansys-optics-kb",
        "doc_type": "kb_article",
        "category": category_name,
        "section": section_name,
        "title": article.get("title"),
        "url": article.get("html_url"),
        "article_id": article.get("id"),
        "updated_at": article.get("updated_at"),
        "parser": "lxml-html",
    }
    base["breadcrumb"] = " > ".join(x for x in [category_name, section_name, article.get("title")] if x)
    return chunk_blocks(html_to_blocks(article.get("body")), base)


def main():
    cats = json.load(open(os.path.join(BASE, "zendesk_categories.json"), encoding="utf-8"))
    secs = json.load(open(os.path.join(BASE, "zendesk_sections.json"), encoding="utf-8"))
    catname = {c["id"]: c.get("name") for c in cats}
    secmap = {s["id"]: s for s in secs}

    out = []
    seen = set()
    articles_total = 0
    for path in sorted(glob.glob(os.path.join(ZEN, "cat_*.json"))):
        arts = json.load(open(path, encoding="utf-8"))
        for a in arts:
            if a.get("draft"):
                continue
            aid = a.get("id")
            if aid in seen:
                continue
            seen.add(aid)
            sec = secmap.get(a.get("section_id"), {})
            sname = sec.get("name", "")
            cname = catname.get(sec.get("category_id"), "")
            articles_total += 1
            for c in chunk_article(a, sname, cname):
                c["id"] = "kb:%s:%s" % (aid, c["meta"]["chunk_idx"])
                out.append(c)

    # .lsf examples: whole file = one chunk
    # .lsf examples: whole file = one chunk if small; large files split by LINES (embedding
    # has an 8192-token input cap -> ~30KB files exceed it). Never split mid-line.
    MAXEX = 4000

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

    lsf_root = os.path.join(CORPUS, "lsf")
    lsf_files = []
    for ext in ("*.lsf", "*.LSF"):
        lsf_files += glob.glob(os.path.join(lsf_root, "**", ext), recursive=True)
    lsf_files = sorted(set(lsf_files))
    for fp in lsf_files:
        rel = os.path.relpath(fp, lsf_root).replace("\\", "/")
        try:
            txt = open(fp, encoding="utf-8", errors="replace").read()
        except Exception:  # noqa: BLE001
            continue
        if not txt.strip():
            continue
        header = "// Lumerical LSF example: %s\n" % rel
        meta = {
            "source": "lumerical-v241-examples",
            "doc_type": "example",
            "path": rel,
            "filename": os.path.basename(rel),
            "parser": "raw",
            "breadcrumb": "Lumerical v241 examples > " + rel,
        }
        parts = split_by_lines(txt, MAXEX)
        if len(parts) == 1:
            out.append({"id": "lsf:" + rel, "text": header + txt, "meta": meta})
        else:
            for k, pt in enumerate(parts):
                m = dict(meta)
                m["part"] = k
                m["parts"] = len(parts)
                m["breadcrumb"] = meta["breadcrumb"] + " [part %d/%d]" % (k + 1, len(parts))
                out.append({"id": "lsf:%s#p%d" % (rel, k),
                            "text": header + "// part %d/%d\n" % (k + 1, len(parts)) + pt,
                            "meta": m})

    outp = os.path.join(CORPUS, "chunks.jsonl")
    with open(outp, "w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps({"id": c["id"], "text": c["text"], "meta": c["meta"]}, ensure_ascii=False) + "\n")

    kb_chunks = sum(1 for c in out if c["meta"]["doc_type"] == "kb_article")
    lsf_chunks = sum(1 for c in out if c["meta"]["doc_type"] == "example")
    total_tok = sum(est_tok(c["text"]) for c in out)
    print("articles=%d kb_chunks=%d lsf_files=%d lsf_chunks=%d TOTAL_CHUNKS=%d"
          % (articles_total, kb_chunks, len(lsf_files), lsf_chunks, len(out)))
    print("est_tokens=%d  avg_chunk_chars=%d" % (total_tok, (sum(len(c["text"]) for c in out) // max(1, len(out)))))
    print("wrote", outp)


if __name__ == "__main__":
    main()

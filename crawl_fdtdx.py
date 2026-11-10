"""Crawl fdtdx documentation into corpus/fdtdx/.

  1. readthedocs: BFS over links under /en/stable/ (sitemap only lists the version root)
  2. GitHub: repo tarball (no API rate limit) -> examples/*.py + docs/*.md|rst + README
Output: corpus/fdtdx/articles.json + corpus/fdtdx/examples/*.py
"""
import html as htmlmod
import io
import json
import os
import re
import tarfile
import time
import urllib.request
from urllib.parse import urljoin, urldefrag

from lxml import html as LH

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Firefox/130.0)"
BASE = "https://fdtdx.readthedocs.io"
START = BASE + "/en/stable/"
OUT = os.path.join(os.path.dirname(__file__), "corpus", "fdtdx")
REPOS = ("ymahlau/fdtdx", "ynahlau/fdtdx")
MAX_PAGES = 250
SKIP = ("_sources", "_static", "_modules", "genindex", "search.html", "py-modindex")


def fetch(url, tries=2, timeout=15):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def md_to_html(md):
    out, code, buf, in_code = [], [], [], False

    def flush():
        if buf:
            out.append("<p>" + htmlmod.escape(" ".join(buf)) + "</p>")
            buf.clear()

    for line in md.splitlines():
        if line.strip().startswith("```"):
            flush()
            if not in_code:
                code, in_code = [], True
            else:
                out.append("<pre><code>" + htmlmod.escape("\n".join(code)) + "</code></pre>")
                in_code = False
            continue
        if in_code:
            code.append(line)
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            lvl = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (lvl, htmlmod.escape(m.group(2).strip()), lvl))
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line.strip())
    flush()
    if in_code:
        out.append("<pre><code>" + htmlmod.escape("\n".join(code)) + "</code></pre>")
    return "\n".join(out)


def page_record(url, raw):
    doc = LH.fromstring(raw)
    t = doc.xpath("//title/text()")
    title = (t[0].strip() if t else url)
    title = re.sub(r"\s*[\u2014-]\s*fdtdx.*$", "", title).strip() or title
    main = (doc.xpath('//div[@role="main"]') or doc.xpath("//article")
            or doc.xpath('//div[contains(@class,"document")]') or doc.xpath("//body"))
    if not main:
        return None, []
    body = LH.tostring(main[0], encoding="unicode")
    links = doc.xpath("//a/@href")
    return ({"id": url, "title": title, "body": body, "html_url": url,
             "category": "fdtdx documentation", "section": "", "kind": "doc"}, links)


def crawl_rtd():
    seen, queue, arts = {START}, [START], []
    while queue and len(arts) < MAX_PAGES:
        u = queue.pop(0)
        try:
            raw = fetch(u)
        except Exception as e:  # noqa: BLE001
            print("  skip", u, e)
            continue
        rec, links = page_record(u, raw)
        if rec and rec["body"].strip():
            arts.append(rec)
            if len(arts) % 25 == 0:
                print("  rtd kept %d (queue %d)" % (len(arts), len(queue)), flush=True)
        for a in links:
            v = urldefrag(urljoin(u, a or ""))[0]
            if not v.startswith(START) or any(s in v for s in SKIP):
                continue
            if v.endswith((".css", ".js", ".png", ".svg", ".jpg", ".zip", ".pdf", ".inv", ".txt")):
                continue
            if v not in seen:
                seen.add(v)
                queue.append(v)
        time.sleep(0.1)
    print("rtd pages kept:", len(arts), "discovered:", len(seen))
    return arts


def crawl_github():
    data, repo = None, None
    for cand in REPOS:
        for url in ("https://codeload.github.com/%s/tar.gz/refs/heads/main" % cand,
                    "https://github.com/%s/archive/refs/heads/main.tar.gz" % cand):
            try:
                data = fetch(url, timeout=120)
                repo = cand
                print("github tarball:", cand, len(data), "bytes")
                break
            except Exception as e:  # noqa: BLE001
                print("  gh try", url, "->", e)
        if data:
            break
    if not data:
        return [], 0
    arts, nex = [], 0
    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    for m in tf.getmembers():
        if not m.isfile():
            continue
        name = m.name.split("/", 1)[1] if "/" in m.name else m.name
        low = name.lower()
        is_ex = low.startswith("examples/") and low.endswith(".py")
        is_md = low.endswith((".md", ".rst")) and (low.startswith("docs/") or "/" not in name)
        if not (is_ex or is_md):
            continue
        raw = tf.extractfile(m).read()
        txt = raw.decode("utf-8", "replace")
        if is_ex:
            fp = os.path.join(OUT, "examples", name.replace("/", "__"))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(txt)
            nex += 1
        else:
            arts.append({"id": "gh:" + name, "title": os.path.basename(name),
                         "body": md_to_html(txt),
                         "html_url": "https://github.com/%s/blob/main/%s" % (repo, name),
                         "category": "fdtdx repository", "section": name, "kind": "doc"})
    print("github examples:", nex, "github md:", len(arts))
    return arts, nex


def main():
    os.makedirs(os.path.join(OUT, "examples"), exist_ok=True)
    arts = crawl_rtd()
    gh, _ = crawl_github()
    arts += gh
    with open(os.path.join(OUT, "articles.json"), "w", encoding="utf-8") as f:
        json.dump(arts, f, ensure_ascii=False)
    print("TOTAL docs=%d -> corpus/fdtdx/articles.json" % len(arts))


if __name__ == "__main__":
    main()



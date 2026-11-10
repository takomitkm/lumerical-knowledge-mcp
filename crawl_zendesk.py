"""Crawl optics.ansys.com Zendesk KB for the Lumerical categories (excluding Installation/Licensing,
Zemax, Speos, ACE). Saves raw article JSON per category for provenance + reproducibility.
"""
import json
import os
import time
import urllib.request
import urllib.parse

API = "https://optics.ansys.com/api/v2/help_center"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/130.0"

INCLUDE = {
    "Application Gallery": "360002993513",
    "System Suite": "360001618173",
    "Scripting Language": "360001998954",
    "DEVICE Suite": "360001618153",
    "Snippets": "47095075105555",
    "Interoperability": "360001994594",
    "How To": "1500000499722",
    "High-Performance Computing": "360002147933",
    "Help": "37093353953171",
    # 扩库(2026-11-10):Zemax / Speos 也纳入
    "Zemax Knowledge Base": "10139548118675",
    "Speos Knowledge Base": "6336944969107",
}

OUT = os.path.join(os.path.dirname(__file__), "corpus", "zendesk")


def get(path, **params):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def crawl_category(name, cid):
    articles = []
    page = 1
    while True:
        d = get("/categories/%s/articles.json" % cid, per_page=100, page=page)
        arts = d.get("articles", [])
        for a in arts:
            articles.append({
                "id": a.get("id"),
                "title": a.get("title"),
                "body": a.get("body"),
                "section_id": a.get("section_id"),
                "html_url": a.get("html_url"),
                "updated_at": a.get("updated_at"),
                "locale": a.get("locale"),
                "draft": a.get("draft"),
            })
        print("  %-32s page %d got %d (count=%s)" % (name, page, len(arts), d.get("count")))
        if not d.get("next_page"):
            break
        page += 1
        time.sleep(0.2)
    path = os.path.join(OUT, "cat_%s.json" % name.replace(" ", "_").replace("/", "_"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False)
    print("%-36s => %d articles -> %s" % (name, len(articles), os.path.basename(path)))
    return len(articles)


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for name, cid in INCLUDE.items():
        print("== %s (%s) ==" % (name, cid))
        total += crawl_category(name, cid)
    print("GRAND_TOTAL=%d" % total)


if __name__ == "__main__":
    main()

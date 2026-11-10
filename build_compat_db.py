"""Build the compatibility layer:
   - compat/compatibility.db      (SQLite: features / recipes / recipe_deps / version_map)
   - corpus/compat/chunks.jsonl   (recipe chunks for the Qdrant `lumerical_compat` collection)

Sources: v241 docs.json (665 commands), latest KB Scripting-Language articles (767 command
pages), and the hand-written recipes in v241-recipes/v241_compat_recipes.lsf.
"""
import json
import os
import re
import sqlite3

from lxml import html as LH

BASE = os.path.dirname(__file__)
V241 = os.path.join(BASE, "corpus", "lumerical_v241", "docs.json")
KB = os.path.join(BASE, "corpus", "zendesk", "cat_Scripting_Language.json")
RECIPE = os.path.join(BASE, "v241-recipes", "v241_compat_recipes.lsf")
DBDIR = os.path.join(BASE, "compat")
DB = os.path.join(DBDIR, "compatibility.db")
CHUNKS = os.path.join(BASE, "corpus", "compat", "chunks.jsonl")

EQUIV = {"findresonances": "approximate", "sort": "exact", "median": "exact", "modeoverlap": "approximate"}


def plain(html: str) -> str:
    if not html:
        return ""
    try:
        t = LH.fromstring("<div>%s</div>" % html).text_content()
    except Exception:  # noqa: BLE001
        t = re.sub(r"<[^>]+>", " ", html)
    return " ".join(t.split())


def main():
    os.makedirs(DBDIR, exist_ok=True)
    os.makedirs(os.path.join(BASE, "corpus", "compat"), exist_ok=True)

    v241 = json.load(open(V241, encoding="utf-8"))
    v241_l = {k.lower(): (k, v) for k, v in v241.items()}

    arts = json.load(open(KB, encoding="utf-8"))
    pat = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*-\s*Script command", re.I)
    kb = {}
    for a in arts:
        m = pat.search((a.get("title") or "").strip())
        if m:
            nm = m.group(1).lower()
            kb[nm] = {"url": a.get("html_url"), "text": plain(a.get("body") or "")[:600],
                      "title": a.get("title")}

    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE features(
      name TEXT PRIMARY KEY,
      in_v241 INTEGER, in_latest INTEGER,
      v241_url TEXT, latest_url TEXT,
      description TEXT, status TEXT);
    CREATE TABLE recipes(
      id TEXT PRIMARY KEY, feature TEXT, title TEXT, target_version TEXT,
      equivalence TEXT, source_path TEXT, code TEXT, notes TEXT);
    CREATE TABLE recipe_deps(
      recipe_id TEXT, command TEXT, PRIMARY KEY(recipe_id, command));
    CREATE TABLE version_map(
      feature TEXT PRIMARY KEY, relation TEXT, counterpart TEXT);
    """)

    names = sorted(set(v241_l) | set(kb))
    for nm in names:
        v = v241_l.get(nm)
        k = kb.get(nm)
        desc = (k["text"] if k and k["text"] else (v[1].get("text", "") if v else ""))[:600]
        cur.execute("INSERT INTO features VALUES(?,?,?,?,?,?,?)", (
            nm, 1 if v else 0, 1 if k else 0,
            (v[1].get("link") if v else None), (k["url"] if k else None),
            desc, "pending"))

    for nm in sorted(set(v241_l) - set(kb)):
        cur.execute("INSERT OR REPLACE INTO version_map VALUES(?,?,?)",
                    (nm, "removed_or_renamed_in_latest", None))
    for nm in sorted(set(kb) - set(v241_l)):
        cur.execute("INSERT OR REPLACE INTO version_map VALUES(?,?,?)", (nm, "new_in_latest", None))

    # ---- recipes ----
    code = open(RECIPE, encoding="utf-8").read()
    parts = re.split(r"^# -+\n# RECIPE ", code, flags=re.M)
    v241keys = set(v241_l)
    chunks = []
    n = 0
    for p in parts[1:]:
        title = p.split("\n", 1)[0].split("\u2014\u2014")[0].split("--")[0].strip()  # "1: findresonances"
        label = title.split(":", 1)[-1].strip()
        feats = [f.strip() for f in label.split("/")]           # "sort / median"
        body = "# RECIPE " + p
        n += 1
        rid = "recipe_%03d" % n
        deps = sorted({m.group(1).lower() for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", body)}
                      & v241keys)
        equiv = "|".join(EQUIV.get(f, "approximate") for f in feats)
        cur.execute("INSERT INTO recipes VALUES(?,?,?,?,?,?,?,?)", (
            rid, feats[0], "v241 compat recipe: " + label, "v241", equiv,
            "v241-recipes/v241_compat_recipes.lsf", body,
            "Emulates newer command(s) [%s] using v241 primitives only." % ", ".join(feats)))
        for d in deps:
            cur.execute("INSERT OR IGNORE INTO recipe_deps VALUES(?,?)", (rid, d))
        for f in feats:
            cur.execute("UPDATE features SET status=? WHERE name=?", ("recipe_available", f))

        text = ("COMPAT RECIPE %s for feature(s): %s\nequivalence: %s\ntarget version: v241\n"
                "v241 dependencies: %s\n\n%s" % (rid, ", ".join(feats), equiv, ", ".join(deps), body))
        chunks.append({
            "id": "compat:%s" % rid,
            "text": text,
            "meta": {"source": "lumerical-compat", "doc_type": "recipe", "version": "v241",
                     "feature": ", ".join(feats), "recipe_id": rid, "equivalence": equiv,
                     "deps": deps, "parser": "manual",
                     "title": "v241 compat recipe: " + label,
                     "url": "local:v241-recipes/v241_compat_recipes.lsf",
                     "breadcrumb": "Lumerical compatibility > %s (v241 recipe)" % ", ".join(feats)},
        })

    # everything else that is new in latest and has no recipe yet
    cur.execute("UPDATE features SET status='no_recipe_yet' WHERE in_v241=0 AND in_latest=1 AND status='pending'")
    cur.execute("UPDATE features SET status='available' WHERE in_v241=1 AND status='pending'")
    con.commit()

    counts = {r[0]: r[1] for r in cur.execute("SELECT status, COUNT(*) FROM features GROUP BY status")}
    print("features:", cur.execute("SELECT COUNT(*) FROM features").fetchone()[0], counts)
    print("recipes:", cur.execute("SELECT COUNT(*) FROM recipes").fetchone()[0])
    print("deps:", cur.execute("SELECT COUNT(*) FROM recipe_deps").fetchone()[0])

    with open(CHUNKS, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print("chunks:", len(chunks), "->", CHUNKS)
    con.close()
    print("db:", DB, os.path.getsize(DB), "bytes")


if __name__ == "__main__":
    main()

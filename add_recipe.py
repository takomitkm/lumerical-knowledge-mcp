"""Verify the recipe's identifiers against v241 docs.json, then emit chunks for ingestion."""
import json
import os
import re

BASE = os.path.dirname(__file__)
DOCS = os.path.join(BASE, "corpus", "lumerical_v241", "docs.json")
SRC = os.path.join(BASE, "v241-recipes", "v241_compat_recipes.lsf")
OUT = os.path.join(BASE, "corpus", "lumerical_v241", "recipes.jsonl")

docs = json.load(open(DOCS, encoding="utf-8"))
keys = {k.lower() for k in docs}
code = open(SRC, encoding="utf-8").read()

# identifiers that look like calls
calls = set(m.group(1).lower() for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", code))
local = {"for", "if", "matrix"}  # loop keywords / not commands
unknown = sorted(c for c in calls if c not in keys and c not in local)
print("identifiers used:", len(calls))
print("NOT in v241 docs.json:", unknown if unknown else "none")

# split into recipes
parts = re.split(r"^# -+\n# RECIPE ", code, flags=re.M)
recs = []
for p in parts[1:]:
    title_line = p.split("\n", 1)[0]
    name = title_line.split("——")[0].split("--")[0].strip()
    body = "# RECIPE " + p
    recs.append((name, body))

out = []
for name, body in recs:
    out.append({
        "id": "v241:recipe:%s" % name.lower().replace(" ", "_"),
        "text": body,
        "meta": {
            "source": "lumerical-v241",
            "doc_type": "recipe",
            "version": "v241",
            "title": "v241 compat recipe: " + name,
            "url": "local:v241-recipes/v241_compat_recipes.lsf",
            "command": name,
            "parser": "manual",
            "breadcrumb": "Lumerical v241 compat recipes > " + name,
        },
    })
with open(OUT, "w", encoding="utf-8") as f:
    for c in out:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
print("recipes:", [r["meta"]["title"] for r in out], "->", OUT)

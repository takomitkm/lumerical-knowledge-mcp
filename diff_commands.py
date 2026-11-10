"""Diff latest-KB script commands vs the v241 docs.json command list."""
import json
import os
import re

BASE = os.path.dirname(__file__)
KB = os.path.join(BASE, "corpus", "zendesk", "cat_Scripting_Language.json")
V241 = os.path.join(BASE, "corpus", "lumerical_v241", "docs.json")

v241 = {k.lower() for k in json.load(open(V241, encoding="utf-8")).keys()}
arts = json.load(open(KB, encoding="utf-8"))

pat = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*-\s*Script command", re.I)
kb_cmds = {}
for a in arts:
    t = (a.get("title") or "").strip()
    m = pat.search(t)
    if m:
        kb_cmds[m.group(1).lower()] = t

only_kb = sorted(set(kb_cmds) - v241)
only_v241 = sorted(v241 - set(kb_cmds))
print("v241 commands: %d   KB command pages: %d" % (len(v241), len(kb_cmds)))
print("in KB but NOT in v241: %d" % len(only_kb))
print("in v241 but no KB command page: %d" % len(only_v241))
print("\n--- NEW-ish commands (KB only) ---")
for c in only_kb:
    print("  ", c)
print("\n--- v241-only (removed/renamed later) sample ---")
print("  " + ", ".join(only_v241[:40]))

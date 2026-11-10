"""Build compatibility.db with the kit schema (10 tables).

Seeds ONLY evidence-backed facts:
- target environment: Lumerical 2024 R1 (v241) as documented by the installation's bundled docs.json
  (solver='shared' because that command list is installation-wide; no runtime capture yet)
- features: union of docs.json commands and latest-KB command pages; kind=language_construct for keywords
- evidence_sources: the two official-document sources we actually used
- feature_availability: 'native' + evidence_basis 'official_docs' ONLY for docs.json entries.
  Anything else gets NO row -> lookups return 'unknown' (documented absence != runtime absence).
Implementations / document_refs / validation_runs arrive in Phase 6.
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

from lxml import html as LH

BASE = os.path.dirname(__file__)
SCHEMA = os.path.join(BASE, "shim", "compat", "schema.sql")
V241 = os.path.join(BASE, "corpus", "lumerical_v241", "docs.json")
KB = os.path.join(BASE, "corpus", "zendesk", "cat_Scripting_Language.json")
OUT = os.path.join(BASE, "compat", "compatibility.db")

KEYWORDS = {"function", "end", "resume", "print", "if", "for", "else", "elseif", "while",
            "break", "continue", "return"}
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def plain(html: str) -> str:
    if not html:
        return ""
    try:
        t = LH.fromstring("<div>%s</div>" % html).text_content()
    except Exception:  # noqa: BLE001
        t = re.sub(r"<[^>]+>", " ", html)
    return " ".join(t.split())


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.replace(OUT, OUT + ".prev")
    con = sqlite3.connect(OUT)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(open(SCHEMA, encoding="utf-8").read())

    v241 = json.load(open(V241, encoding="utf-8"))
    v241_l = {k.lower(): (k, v) for k, v in v241.items()}

    arts = json.load(open(KB, encoding="utf-8"))
    pat = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*-\s*Script command", re.I)
    kb = {}
    for a in arts:
        m = pat.search((a.get("title") or "").strip())
        if m:
            kb[m.group(1).lower()] = {"url": a.get("html_url"), "text": plain(a.get("body") or "")[:800]}

    # ---- target environment ----
    target_id = "lumerical-2024r1-install"
    con.execute(
        "INSERT OR REPLACE INTO target_environments(target_id, product, solver, version_label, "
        "update_label, build_number, platform, captured_at, capture_notes) VALUES(?,?,?,?,?,?,?,?,?)",
        (target_id, "Lumerical", "shared", "2024 R1", "", "v241", None, None,
         "Documentation-only target derived from the installation's bundled api/python/docs.json. "
         "solver='shared' because that command list is installation-wide. No runtime capture yet; "
         "runtime availability stays unknown until a getcommands snapshot exists."))

    # ---- evidence sources ----
    con.execute("INSERT OR REPLACE INTO evidence_sources VALUES(?,?,?,?,?,?,?,?)",
                ("docs-json-v241", "official_command_doc", "ansys",
                 "Lumerical v241 bundled docs.json (665 commands)", None, "2024 R1", "2024 R1",
                 "Path: <install>/api/python/docs.json copied from the school install."))
    con.execute("INSERT OR REPLACE INTO evidence_sources VALUES(?,?,?,?,?,?,?,?)",
                ("kb-scripting-latest", "official_command_doc", "ansys",
                 "optics.ansys.com Scripting Language KB (current)", "https://optics.ansys.com/hc/en-us",
                 "current", "current", "Command pages scraped from the help-centre API."))

    # ---- features + documented availability ----
    names = sorted(set(v241_l) | set(kb))
    n_feat = n_native = 0
    for nm in names:
        v = v241_l.get(nm)
        k = kb.get(nm)
        kind = "language_construct" if nm in KEYWORDS else "command"
        desc = (k["text"] if k else v[1].get("text", ""))[:800] or None
        fid = "feat:%s" % nm
        con.execute("INSERT OR REPLACE INTO features(feature_id, canonical_name, feature_kind, "
                    "description) VALUES(?,?,?,?)", (fid, nm, kind, desc))
        n_feat += 1
        if v:  # documented in the v241 install -> documented-native (NOT a runtime claim)
            con.execute(
                "INSERT OR REPLACE INTO feature_availability(feature_id, target_id, status, "
                "evidence_basis, source_id, snapshot_id, checked_at, notes) VALUES(?,?,?,?,?,?,?,?)",
                (fid, target_id, "native", "official_docs", "docs-json-v241", None, NOW,
                 "Listed in the bundled v241 docs.json. Documentation evidence only; "
                 "runtime presence not yet captured."))
            n_native += 1

    # ---- evidence seed from the kit (source-history records; REQUIRED) ----
    # The kit zip is not publicly distributed. Without it this build loses the
    # source-history evidence (release-note IDs that availability rows reference via FK)
    # and the ten seed feature rows -> downstream evidence corrections fail.
    seed = os.path.join(BASE, "_kit", "lumerical_compat_backport_kit", "schema", "evidence_seed.sql")
    if not os.path.exists(seed):
        sys.exit(
            "FATAL: kit evidence seed not found at %s\n"
            "  The kit ships with this repository under _kit/. If it is missing, the\n"
            "  checkout is incomplete - restore _kit/lumerical_compat_backport_kit/\n"
            "  (schema/, tasks/, docs/, templates/). Building without the seed would\n"
            "  silently drop the source-history evidence rows (ansys.sort /\n"
            "  ansys.findresonances / release-note sources) that feature_availability\n"
            "  foreign keys reference." % seed)

    # ---- documentation-gap corrections (NOT runtime claims) ----
    # sort/findresonances/modeoverlap were introduced BEFORE 2024 R1 (2018a R6 / 2019a /
    # 2022 R2.2). Their absence from the v241 docs.json is a documentation gap, so record an
    # 'unknown' availability row carrying that evidence instead of leaving nothing.
    gaps = [
        ("sort", "ansys.sort",
         "Official page states sort was introduced 2018a R6, which predates 2024 R1; the "
         "bundled v241 docs.json omission is a documentation gap, not evidence of absence. "
         "Runtime presence not yet captured (no getcommands snapshot)."),
        ("findresonances", "ansys.findresonances",
         "Official page and 2019a release notes place findresonances at 2019a, predating "
         "2024 R1; the docs.json omission is a documentation gap. Runtime presence not yet "
         "captured (no getcommands snapshot)."),
        ("modeoverlap", "ansys.release.2022r2.2",
         "2022 R2.2 release notes introduce modeoverlap (FEEM/DGTD raw mode/field data), "
         "predating 2024 R1; the docs.json omission is a documentation gap. Solver scope is "
         "product-specific. Runtime presence not yet captured."),
    ]
    for nm, src, note in gaps:
        fid = "feat:%s" % nm
        if con.execute("SELECT 1 FROM features WHERE feature_id=?", (fid,)).fetchone():
            con.execute(
                "INSERT OR REPLACE INTO feature_availability(feature_id, target_id, status, "
                "evidence_basis, source_id, snapshot_id, checked_at, notes) VALUES(?,?,?,?,?,?,?,?)",
                (fid, target_id, "unknown", "official_docs", src, None, NOW, note))

    con.commit()
    counts = {t: con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in
              ("target_environments", "features", "feature_availability", "evidence_sources")}
    print("db:", OUT, os.path.getsize(OUT), "bytes")
    print(counts)
    print("documented-native:", n_native, "/", n_feat,
          " (the rest stay 'unknown' until a runtime snapshot exists)")
    con.close()


if __name__ == "__main__":
    main()

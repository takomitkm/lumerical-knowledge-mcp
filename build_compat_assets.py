"""Build compatibility assets: validate authoring files, register them in SQLite, and emit
ONE retrievable document per asset (recipe.md + the complete LSF source, never split).

Run with a python that has PyYAML (the docling venv works).
"""
import glob
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

import yaml

BASE = os.path.dirname(__file__)
ASSETS = os.path.join(BASE, "compat", "assets")
DB = os.path.join(BASE, "compat", "compatibility.db")
CHUNKS = os.path.join(BASE, "compat", "asset_chunks.jsonl")
DOCS_JSON = os.path.join(BASE, "corpus", "lumerical_v241", "docs.json")
COLLECTION = "lumerical_compat"

REQUIRED_META = ["doc_id", "doc_type", "source_type", "authority", "product", "solver",
                 "version_scope", "target_version", "feature_id", "implementation_id",
                 "equivalence", "verification_level", "status", "dependencies",
                 "preconditions", "limitations"]
EQUIV = {"exact", "domain_equivalent", "approximate", "partial", "unsupported"}
LEVELS = {"L0", "L1", "L2", "L3", "L4"}
STATUS = {"draft", "candidate", "static_checked", "runtime_verified",
          "differential_verified", "proven", "blocked", "deprecated"}
KINDS = {"native", "adapter", "backport", "workaround"}
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def point_id(cid: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "%s:%s" % (COLLECTION, cid)))


def main():
    known = {k.lower() for k in json.load(open(DOCS_JSON, encoding="utf-8"))}
    # runtime-captured symbols are ALSO valid dependency evidence (docs.json has gaps at v241)
    runtime_known = set()
    snap_db = os.path.join(BASE, "compat", "compatibility.db")
    try:
        import sqlite3
        _c = sqlite3.connect(snap_db)
        runtime_known = {r[0].lower() for r in _c.execute(
            "SELECT symbol FROM capability_items WHERE presence='present'")}
        _c.close()
    except Exception:  # noqa: BLE001
        pass
    known = known | runtime_known
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")

    chunks, problems = [], []
    for d in sorted(glob.glob(os.path.join(ASSETS, "*"))):
        if not os.path.isdir(d):
            continue
        impl_f = os.path.join(d, "implementation.yaml")
        recipe_f = os.path.join(d, "recipe.md")
        lsf_f = os.path.join(d, "implementation.lsf")
        if not (os.path.exists(impl_f) and os.path.exists(recipe_f) and os.path.exists(lsf_f)):
            problems.append("%s: missing implementation.yaml / recipe.md / implementation.lsf" % d)
            continue

        meta = yaml.safe_load(open(impl_f, encoding="utf-8"))
        impl_id = meta["implementation_id"]
        recipe_doc_id = meta["implementation"].get("recipe_doc_id") or impl_id
        feat_name = meta["feature"]["canonical_name"]
        feat_id = meta["feature"]["feature_id"]
        target = meta["target"]
        # explicit target_id wins; else fall back to the docs-derived environment
        tgt_id = target.get("target_id") or "lumerical-2024r1-install"
        impl = meta["implementation"]

        # --- enum / consistency validation ---
        for key, allowed in (("equivalence", EQUIV), ("verification_level", LEVELS),
                             ("status", STATUS), ("kind", KINDS)):
            if impl.get(key) not in allowed:
                problems.append("%s: %s=%r not in %s" % (impl_id, key, impl.get(key), sorted(allowed)))

        # --- static identifier check against the v241 docs.json ---
        deps = meta.get("dependencies") or []
        for dep in deps:
            if dep.get("type") in ("command", "keyword") and dep["name"].lower() not in known:
                problems.append("%s: dependency %r not in docs.json" % (impl_id, dep["name"]))

        code = open(lsf_f, encoding="utf-8").read()
        recipe_md = open(recipe_f, encoding="utf-8").read()
        text = (recipe_md.rstrip() + "\n\n## Full LSF source (implementation.lsf)\n\n```lsf\n"
                + code.rstrip() + "\n```\n")
        deps_summary = ", ".join("%s(%s)" % (x["name"], x.get("type", "?")) for x in deps)
        cid = "compatdoc:%s" % impl_id

        # --- SQLite: document_refs + implementations + deps ---
        con.execute("INSERT OR REPLACE INTO document_refs(doc_id, collection, doc_type, title, "
                    "source_path, source_id, qdrant_point_id, metadata_json) VALUES(?,?,?,?,?,?,?,?)",
                    (recipe_doc_id, COLLECTION, "compatibility_recipe",
                     "Compatibility recipe: %s (%s)" % (feat_name, target["version_label"]),
                     os.path.relpath(lsf_f, BASE), "docs-json-v241", point_id(cid),
                     json.dumps({"equivalence": impl["equivalence"],
                                 "verification_level": impl["verification_level"]})))
        con.execute(
            "INSERT OR REPLACE INTO implementations(implementation_id, feature_id, target_id, "
            "implementation_kind, equivalence, verification_level, status, recipe_doc_id, "
            "source_path, contract_json, preconditions, assumptions, limitations, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (impl_id, feat_id, tgt_id, impl["kind"], impl["equivalence"],
             impl["verification_level"], impl["status"], recipe_doc_id,
             os.path.relpath(lsf_f, BASE), json.dumps(meta.get("contract") or {}),
             "\n".join(meta.get("preconditions") or []),
             "\n".join(meta.get("assumptions") or []),
             "\n".join(meta.get("limitations") or []), NOW))
        con.execute("DELETE FROM implementation_dependencies WHERE implementation_id = ?", (impl_id,))
        for dep in deps:
            con.execute(
                "INSERT OR REPLACE INTO implementation_dependencies(implementation_id, dependency_name,"
                " dependency_type, required, target_presence, evidence_source_id) VALUES(?,?,?,?,?,?)",
                (impl_id, dep["name"], dep.get("type", "command"), 1 if dep.get("required", True) else 0,
                 dep.get("target_presence", "unknown"), "docs-json-v241"))

        # --- SQLite: validation runs from test-report*.json ---
        for tr in sorted(glob.glob(os.path.join(d, "test-report*.json"))):
            rep = json.load(open(tr, encoding="utf-8"))
            con.execute(
                "INSERT OR REPLACE INTO validation_runs(validation_run_id, implementation_id, target_id,"
                " test_suite_id, test_method, result, run_at, runner, report_path, metrics_json, notes) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (rep["validation_run_id"], impl_id, rep.get("target_id", "lumerical-2024r1-install"),
                 rep.get("test_suite_id"), rep["test_method"], rep["result"], rep["run_at"],
                 rep.get("runner"), os.path.relpath(tr, BASE), json.dumps(rep.get("metrics") or {}),
                 rep.get("notes")))

        # --- retrieval document (whole, not split) ---
        cm = {
            "doc_id": recipe_doc_id, "doc_type": "compatibility_recipe", "source_type": "user_authored",
            "authority": "project", "source_url": None,
            "source_title": "compat asset %s" % impl_id,
            "product": "Lumerical", "solver": "shared",
            "version_scope": target["version_label"], "target_version": target["version_label"],
            "tested_version": None, "introduced_version": None, "removed_version": None,
            "feature_id": feat_id, "implementation_id": impl_id,
            "equivalence": impl["equivalence"], "verification_level": impl["verification_level"],
            "status": impl["status"], "dependencies": deps_summary,
            "preconditions": meta.get("preconditions") or [],
            "limitations": meta.get("limitations") or [],
            "title": "Compatibility recipe: %s (%s)" % (feat_name, target["version_label"]),
            "url": "local:compat/assets/%s" % os.path.basename(d),
            "breadcrumb": "Lumerical compatibility > %s > %s" % (feat_name, impl_id),
            "chunk_idx": 0, "parser": "manual",
        }
        missing = [k for k in REQUIRED_META if k not in cm]
        if missing:
            problems.append("%s: missing payload keys %s" % (impl_id, missing))
        chunks.append({"id": cid, "text": text, "meta": cm})

    con.commit()
    with open(CHUNKS, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print("assets:", len(chunks), "->", CHUNKS)
    print("impls:", con.execute("SELECT COUNT(*) FROM implementations").fetchone()[0],
          "deps:", con.execute("SELECT COUNT(*) FROM implementation_dependencies").fetchone()[0],
          "docrefs:", con.execute("SELECT COUNT(*) FROM document_refs").fetchone()[0],
          "runs:", con.execute("SELECT COUNT(*) FROM validation_runs").fetchone()[0])
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  -", p)
    con.close()
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()


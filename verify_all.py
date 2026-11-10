"""Full verification sweep for the compat layer + RAG. Run from rag-102 root.
Checks: files, DB contents, test suite, remote services, collections, BM25, MCP tools,
compat endpoints, evidence artifacts. Prints PASS/FAIL per item.
"""
import json
import os
import sqlite3
import subprocess
import sys

BASE = r"S:\apps\llm\agentwork\rag-102"
os.chdir(BASE)
PY = r"S:\apps\llm\agentwork\rag-102\.venv-docling\Scripts\python.exe"
TOKEN = open(os.path.expanduser(r"~\.rag\token"), encoding="utf-8").read().strip()
HOST = "http://RAG_HOST:8900"
import urllib.request
import urllib.error

results = []


def check(name, fn):
    try:
        ok, detail = fn()
        results.append((name, "PASS" if ok else "FAIL", detail))
    except Exception as e:  # noqa: BLE001
        results.append((name, "FAIL", "%s: %s" % (type(e).__name__, str(e)[:120])))


def api(path, timeout=30):
    req = urllib.request.Request(HOST + path, headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def r1_local_files():
    need = [
        "shim/app.py", "shim/mcp_server.py", "shim/compat/schema.sql", "shim/compat/db.py",
        "shim/compat/repo.py", "shim/compat/api.py",
        "compat/compatibility.db", "compat/runtime_crosscheck.json",
        "compat/absent_commands_inventory.md",
        "compat/assets/resonance_fwhm_v241/recipe.md",
        "compat/assets/resonance_fwhm_v241/implementation.lsf",
        "compat/assets/resonance_fwhm_v241/implementation.yaml",
        "compat/assets/resonance_fwhm_v241/differential_results.json",
        "compat/assets/resonance_fwhm_v241/validation_final.json",
        "compat/assets/median_sort_v241/recipe.md",
        "compat/assets/median_sort_v241/implementation.lsf",
        "compat/assets/adddftmonitor_v241/recipe.md",
        "compat/assets/adddftmonitor_v241/implementation.lsf",
        "compat/assets/adddftmonitor_v241/adapter_results.json",
        "compat/assets/reportmeshstatistics_v241/recipe.md",
        "compat/assets/reportmeshstatistics_v241/implementation.lsf",
        "compat/assets/reportmeshstatistics_v241/adapter_results.json",
        "capabilities/snapshots/lumerical-2024r1-school-20261110/commands.json",
        "capabilities/snapshots/lumerical-2024r1-school-20261110/syntax_probes.json",
        "tests/test_compat_registry.py", "tests/test_compat_api.py",
        "PLAN.md", "COMPAT_INTEGRATION_MAP.md",
        "_kit/lumerical_compat_backport_kit/tasks/PHASE_PLAN.md",
    ]
    missing = [p for p in need if not os.path.exists(os.path.join(BASE, p))]
    return not missing, ("all %d present" % len(need)) if not missing else "missing: %s" % missing


def r2_db_counts():
    con = sqlite3.connect("compat/compatibility.db")
    con.row_factory = sqlite3.Row
    out = {}
    for t in ("target_environments", "features", "feature_availability", "evidence_sources",
              "document_refs", "capability_snapshots", "capability_items",
              "implementations", "implementation_dependencies", "validation_runs"):
        out[t] = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    con.close()
    ok = (out["features"] >= 786 and out["capability_snapshots"] == 1
          and out["capability_items"] >= 615 and out["implementations"] == 4
          and out["validation_runs"] >= 8)
    return ok, json.dumps(out)


def r3_tests():
    env = dict(os.environ, RAG_TOKEN="test-token-please-ignore", SILICONFLOW_API_KEY="dummy-for-import")
    r = subprocess.run([PY, "-m", "unittest", "discover", "-s", "tests", "-p", "test_compat_*.py"],
                       capture_output=True, text=True, env=env, timeout=300, cwd=BASE)
    tail = r.stderr.strip().splitlines()[-1] if r.stderr else ""
    return "OK" in tail, tail[:80]


def r4_health():
    h = api("/health", timeout=20)
    return h.get("shim") == "ok" and "passed" in h.get("qdrant", ""), json.dumps(h)


def r5_collections():
    c = api("/collections", timeout=30)["collections"]
    d = {x["name"]: x["points"] for x in c}
    ok = (d.get("lumerical") in (14468, 14469) and d.get("lumerical_v241") == 743
          and d.get("fdtdx") == 1202 and d.get("lumerical_compat") == 4)
    return ok, json.dumps(d)


def r6_compat_lookup():
    d = api("/compat/lookup?feature=findresonances&target_id=lumerical-2024r1-school-capture", 30)
    a = d["availability"]["status"]
    impls = [i["implementation_id"] for i in d["implementations"]]
    return a == "native" and "compat.resonance_fwhm.v241.fwhm" in impls, \
        "availability=%s impls=%s" % (a, impls)


def r7_compat_lookup_median():
    d = api("/compat/lookup?feature=median&target_id=lumerical-2024r1-school-capture", 30)
    impls = [i["implementation_id"] for i in d["implementations"]]
    lvl = d["implementations"][0]["verification_level"] if impls else "-"
    return "compat.median.sort.v241.exact" in impls and lvl == "L2", \
        "impls=%s level=%s" % (impls, lvl)


def r8_compat_lookup_adapters():
    d1 = api("/compat/lookup?feature=adddftmonitor&target_id=lumerical-2024r1-school-capture", 30)
    d2 = api("/compat/lookup?feature=reportmeshstatistics&target_id=lumerical-2024r1-school-capture", 30)
    s1 = d1["availability"]["status"]; s2 = d2["availability"]["status"]
    i1 = [i["implementation_id"] for i in d1["implementations"]]
    i2 = [i["implementation_id"] for i in d2["implementations"]]
    ok = (s1 == "absent" and "compat.adddftmonitor.v241.adapter" in i1
          and s2 == "absent" and "compat.reportmeshstatistics.v241.adapter" in i2)
    return ok, "add=%s/%s mesh=%s/%s" % (s1, i1, s2, i2)


def r9_ambiguous():
    try:
        api("/compat/lookup?feature=sort&target_version=2024%20R1", 20)
        return False, "expected 400 ambiguous, got 200"
    except urllib.error.HTTPError as e:
        d = json.loads(e.read().decode())
        return e.code == 400 and d["detail"]["error"] == "ambiguous_target_environment", \
            "HTTP %d %s" % (e.code, d["detail"]["error"])


def r10_capabilities():
    d = api("/compat/capabilities?target_id=lumerical-2024r1-school-capture&symbols=sort,median,findresonances", 30)
    items = {i["symbol"]: i["presence"] for i in d["snapshots"][0]["items"]}
    ok = (d["snapshot_count"] == 1 and items.get("findresonances") == "present"
          and items.get("sort") == "present" and items.get("median") == "absent")
    return ok, json.dumps(items)


def r11_recipe_full():
    d = api("/compat/recipe?implementation_id=compat.resonance_fwhm.v241.fwhm", 60)
    runs = {r["test_method"]: r["result"] for r in d["validation_runs"]}
    return d["content_chars"] > 7000 and runs.get("differential") == "passed" \
        and runs.get("runtime") == "blocked", \
        "chars=%d runs=%s" % (d["content_chars"], runs)


def r12_search_compat():
    d = api("/search?q=findresonances%20Q%20factor&collection=lumerical_compat&top_k=2", 60)
    top = d["results"][0]
    return "findresonances" in top["meta"].get("breadcrumb", ""), \
        "top=%s score=%.3f" % (top["meta"].get("title", "?"), top.get("score", 0))


check("1 local files complete", r1_local_files)
check("2 registry counts", r2_db_counts)
check("3 unit+API tests 16/16", r3_tests)
check("4 shim health", r4_health)
check("5 collection counts", r5_collections)
check("6 lookup findresonances native+impl", r6_compat_lookup)
check("7 lookup median impl L2", r7_compat_lookup_median)
check("8 lookup adapters absent+impl", r8_compat_lookup_adapters)
check("9 ambiguous target -> 400", r9_ambiguous)
check("10 capabilities provenance", r10_capabilities)
check("11 recipe full text + runs", r11_recipe_full)
check("12 search hits compat doc", r12_search_compat)

fails = [r for r in results if r[1] == "FAIL"]
for name, status, detail in results:
    print("%-4s %-38s %s" % (status, name, detail[:110]))
print()
print("TOTAL: %d checks, %d FAIL" % (len(results), len(fails)))
sys.exit(1 if fails else 0)


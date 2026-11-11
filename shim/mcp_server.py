"""MCP server exposing the Lumerical RAG as a tool, for magpie -> dsh.
Thin wrapper: calls the local rag-shim /search over HTTP (same box, loopback).
Run: streamable-http on 0.0.0.0:8901 (endpoint /mcp). Env from rag.env.
"""
import os
import httpx
from mcp.server.fastmcp import FastMCP

SHIM = os.environ.get("RAG_INTERNAL", "http://127.0.0.1:8900").rstrip("/")
TOKEN = os.environ["RAG_TOKEN"]
DEFAULT_COLLECTION = os.environ.get("DEFAULT_COLLECTION", "lumerical")

mcp = FastMCP("lumerical-knowledge-mcp", host="0.0.0.0", port=8901)


@mcp.tool()
def search_lumerical_docs(query: str, top_k: int = 8, collection: str = DEFAULT_COLLECTION,
                          doc_type: str = "") -> str:
    """Search the Lumerical / Ansys Optics knowledge base and local .lsf example scripts.

    Use for ANY Lumerical question: FDTD / MODE / DEVICE / INTERCONNECT / CHARGE / HEAT,
    scripting commands (setnamed, addmode, ...), materials, monitors, sweeps, meshing,
    bandstructure, ring resonators, etc. Returns the top matched passages, each with a
    breadcrumb (category > section > title), the official URL, and body text.

    Args:
        query: natural-language or keyword query, e.g. "how to set mesh accuracy in FDTD".
        top_k: number of passages to return (default 8).
        collection: "lumerical" (default, current KB) | "lumerical_v241" (v241 exact command
            reference from the school install) | "fdtdx" (open-source JAX FDTD library).
        doc_type: optional filter: "command" | "kb_article" | "example" | "api" | "paper" | "doc".
    """
    params = {"q": query, "top_k": top_k, "collection": collection}
    if doc_type:
        params["doc_type"] = doc_type
    r = httpx.get(
        f"{SHIM}/search",
        params=params,
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=120,
    )
    r.raise_for_status()
    d = r.json()
    if not d.get("results"):
        return "No results."
    out = []
    for i, h in enumerate(d["results"], 1):
        m = h.get("meta", {}) or {}
        sc = h.get("score")
        head = f"[{i}] score={sc:.4f}" if isinstance(sc, (int, float)) else f"[{i}]"
        out.append("%s\n%s\n%s\n%s" % (
            head, m.get("breadcrumb", ""), m.get("url", ""), (h.get("text", "") or "")[:1000]))
    return "\n\n---\n\n".join(out)


@mcp.tool()
def get_document(url: str, collection: str = "", max_chars: int = 8000) -> str:
    """Fetch the FULL text of one document by its URL (reassembled from all its chunks).

    Use after search when a snippet is not enough, e.g. url="https://optics.ansys.com/hc/en-us/
    articles/360034924353-addmode-Script-command". Pass collection when known, otherwise all
    collections are searched for that URL.

    Args:
        url: exact URL as returned by search (meta.url / the line under the breadcrumb).
        collection: optional: "lumerical" | "lumerical_v241" | "fdtdx".
        max_chars: truncate the returned text (default 8000).
    """
    params = {"url": url}
    if collection:
        params["collection"] = collection
    r = httpx.get(f"{SHIM}/document", params=params,
                  headers={"Authorization": f"Bearer {TOKEN}"}, timeout=120)
    if r.status_code == 404:
        return "not found: %s" % url
    r.raise_for_status()
    d = r.json()
    text = d.get("text", "") or ""
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]"
    m = d.get("meta", {}) or {}
    return "%s\n%s\nchunks=%s chars=%s\n\n%s" % (
        m.get("breadcrumb", ""), url, d.get("count"), d.get("chars"), text)


@mcp.tool()
def list_collections() -> str:
    """List the available knowledge collections and their point counts."""
    r = httpx.get(f"{SHIM}/collections", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)
    r.raise_for_status()
    return "\n".join("- %s: %s chunks" % (c["name"], c["points"]) for c in r.json()["collections"])


@mcp.tool()
def lookup_lumerical_compatibility(feature: str, target_version: str = "",
                                   product: str = "", solver: str = "",
                                   target_id: str = "") -> str:
    """Is a Lumerical feature available in an EXACT target environment, and what fallbacks exist?

    Answers three questions separately: (1) what the feature is, (2) whether it is natively
    available in the exact product/solver/version, (3) whether a validated backport exists.
    Missing evidence is reported as 'unknown', never as 'absent'.

    Args:
        feature: command or feature name, e.g. "findresonances" / "sort" / "median".
        target_version: exact version label, e.g. "2024 R1" (NOT "v241").
        product: optional product label, e.g. "Lumerical".
        solver: optional solver label as recorded, e.g. "shared".
        target_id: optional exact target id (wins over the filters when several recorded
                   targets share the same nominal version, e.g. a docs-derived one and a
                   runtime capture). Ids are listed in a 400 ambiguous_target response.
    """
    params = {"feature": feature}
    if target_version:
        params["target_version"] = target_version
    if product:
        params["product"] = product
    if solver:
        params["solver"] = solver
    if target_id:
        params["target_id"] = target_id
    r = httpx.get(f"{SHIM}/compat/lookup", params=params,
                  headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)
    if r.status_code == 404:
        try:
            return "not found: %s" % str(r.json().get("detail"))[:400]
        except Exception:  # noqa: BLE001
            return "not found: %s" % feature
    r.raise_for_status()
    d = r.json()
    f, t, a = d["feature"], d["target"], d["availability"]
    lines = ["feature: %s (%s)" % (f["canonical_name"], f["feature_kind"]),
             "target: %s / %s / %s" % (t["product"], t["solver"], t["version"]),
             "availability: %s  basis=%s" % (a["status"],
                                             ",".join(a.get("evidence_basis") or []) or "-")]
    if a.get("notes"):
        lines.append("  note: %s" % a["notes"])
    if f.get("description"):
        lines.append("description: %s" % f["description"][:300])
    if d["implementations"]:
        lines.append("implementations:")
        for i in d["implementations"]:
            lines.append("  - %s  kind=%s  equivalence=%s  verification=%s  status=%s"
                         % (i["implementation_id"], i["kind"], i["equivalence"],
                            i["verification_level"], i["status"]))
            if i.get("limitations"):
                lines.append("      limitations: %s" % str(i["limitations"]).replace("\n", "; "))
    else:
        lines.append("implementations: none recorded")
    if d.get("required_next_evidence"):
        lines.append("required next evidence: " + "; ".join(d["required_next_evidence"]))
    return "\n".join(lines)


@mcp.tool()
def get_lumerical_compat_recipe(implementation_id: str) -> str:
    """Fetch a compatibility recipe by its stable implementation id.

    Returns the full authored document (contract, algorithm, limitations, complete LSF source),
    the dependency list with target evidence, and the recorded validation runs.

    Args:
        implementation_id: e.g. "compat.resonance_fwhm.v241.fwhm"
                           (ids come from lookup_lumerical_compatibility).
    """
    r = httpx.get(f"{SHIM}/compat/recipe", params={"implementation_id": implementation_id},
                  headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)
    if r.status_code == 404:
        try:
            return "not found: %s" % str(r.json().get("detail"))[:300]
        except Exception:  # noqa: BLE001
            return "not found: %s" % implementation_id
    r.raise_for_status()
    d = r.json()
    i = d["implementation"]
    runs = ", ".join("%s:%s" % (x["test_method"], x["result"]) for x in d.get("validation_runs") or [])
    head = ("%s\nfeature=%s  target=%s/%s %s\nkind=%s  equivalence=%s  verification=%s  status=%s\n"
            "validation=%s\ndeps=%s" % (
                implementation_id, i["feature"], i["target"]["product"], i["target"]["solver"],
                i["target"]["version"], i["kind"], i["equivalence"], i["verification_level"],
                i["status"], runs or "none",
                ", ".join(x["dependency_name"] for x in d.get("dependencies") or []) or "none"))
    body = d.get("content") or ""
    if not body:
        body = "[content unavailable: %s]" % d.get("content_error")
    return head + "\n\n" + body


if __name__ == "__main__":
    mcp.run(transport="streamable-http")


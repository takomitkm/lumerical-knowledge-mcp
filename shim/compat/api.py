"""Compatibility REST endpoints (read-only), mounted into the existing rag-shim app.

Auth and document retrieval are injected from app.py so this module reuses the existing
Bearer dependency and the existing Qdrant document path (no second auth system, no
filesystem reads from caller input).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException

from . import db as cdb
from . import repo

router = APIRouter()

_auth_fn = None
_doc_fetcher = None


def bind_auth(fn) -> None:
    global _auth_fn
    _auth_fn = fn


def bind_doc_fetcher(fn) -> None:
    global _doc_fetcher
    _doc_fetcher = fn


def _auth(authorization: Optional[str]) -> None:
    if _auth_fn is None:  # fail closed
        raise HTTPException(503, "compat module not wired")
    _auth_fn(authorization)


def _conn():
    conn = cdb.connect()
    cdb.init_db(conn)  # idempotent; keeps a fresh deployment usable
    return conn


def _target_or_404(rows: List[Dict[str, Any]], product, solver, version):
    if not rows:
        raise HTTPException(404, detail={
            "error": "unknown_target_environment",
            "message": "no recorded target environment for product=%r solver=%r version=%r"
                       % (product, solver, version),
            "hint": "capture a capability snapshot first; absence of a record is NOT proof "
                    "that the feature is missing at runtime",
        })
    if len(rows) > 1:
        raise HTTPException(400, detail={
            "error": "ambiguous_target_environment",
            "message": "multiple targets match; pass product and solver explicitly",
            "candidates": [{"target_id": r["target_id"], "product": r["product"],
                            "solver": r["solver"], "version": r["version_label"],
                            "update": r["update_label"]} for r in rows],
        })
    return rows[0]


@router.get("/compat/lookup")
def compat_lookup(feature: str, target_version: Optional[str] = None,
                  target_id: Optional[str] = None,
                  product: Optional[str] = None, solver: Optional[str] = None,
                  update: Optional[str] = None,
                  authorization: Optional[str] = Header(None)):
    """Is <feature> available in the exact target environment, and what fallbacks exist?

    Pass target_id when two recorded targets share the same nominal product/solver/version
    (e.g. a docs-derived environment and a runtime capture); target_id wins over the filters.
    """
    _auth(authorization)
    if not feature or not (target_id or target_version):
        raise HTTPException(400, detail={"error": "missing_parameter",
                                         "message": "feature and (target_id or target_version)"
                                                    " are required"})
    conn = _conn()

    feat = repo.resolve_feature(conn, feature)
    if feat is None:
        raise HTTPException(404, detail={"error": "unknown_feature", "message": feature,
                                         "hint": "call /compat/capabilities after capturing "
                                                 "a runtime snapshot, or search collection "
                                                 "'lumerical_compat'"})
    if target_id:
        tgt = repo.get_target(conn, target_id)
        if tgt is None:
            raise HTTPException(404, detail={"error": "unknown_target", "message": target_id})
    else:
        targets = repo.resolve_targets(conn, product, solver, target_version, update)
        tgt = _target_or_404(targets, product, solver, target_version)

    avail = repo.availability(conn, feat["feature_id"], tgt["target_id"])
    if avail is None:
        availability = {
            "status": "unknown",
            "evidence_basis": [],
            "notes": "No availability record for this feature/target. Not evidence of absence.",
        }
    else:
        availability = {
            "status": avail["status"],
            "evidence_basis": [avail["evidence_basis"]] if avail["evidence_basis"] else [],
            "checked_at": avail["checked_at"],
            "snapshot_id": avail["snapshot_id"],
            "source": {"title": avail.get("source_title"), "url": avail.get("source_url")},
            "notes": avail.get("notes"),
        }

    impls = []
    for i in repo.implementations(conn, feat["feature_id"], tgt["target_id"]):
        deps = repo.dependencies(conn, i["implementation_id"])
        impls.append({
            "implementation_id": i["implementation_id"],
            "kind": i["implementation_kind"],
            "equivalence": i["equivalence"],
            "verification_level": i["verification_level"],
            "status": i["status"],
            "recipe_doc_id": i["recipe_doc_id"],
            "preconditions": i["preconditions"],
            "assumptions": i["assumptions"],
            "limitations": i["limitations"],
            "dependencies": deps,
        })

    required = []
    if availability["status"] == "unknown":
        required = ["runtime '?getcommands;' snapshot for %s/%s %s"
                    % (tgt["product"], tgt["solver"], tgt["version_label"]),
                    "syntax/keyword probe and signature probe for the same target"]

    return {
        "feature": {
            "feature_id": feat["feature_id"],
            "canonical_name": feat["canonical_name"],
            "query_name": feature,
            "feature_kind": feat["feature_kind"],
            "aliases": repo.feature_aliases(conn, feat["feature_id"]),
            "description": feat["description"],
        },
        "target": {
            "target_id": tgt["target_id"], "product": tgt["product"], "solver": tgt["solver"],
            "version": tgt["version_label"], "update": tgt["update_label"],
            "build": tgt["build_number"],
        },
        "availability": availability,
        "implementations": impls,
        "required_next_evidence": required,
    }


@router.get("/compat/recipe")
def compat_recipe(implementation_id: Optional[str] = None,
                  feature: Optional[str] = None, target_version: Optional[str] = None,
                  product: Optional[str] = None, solver: Optional[str] = None,
                  authorization: Optional[str] = Header(None)):
    """Full recipe (code + contract + evidence) for a stable implementation id."""
    _auth(authorization)
    if not implementation_id and not (feature and target_version):
        raise HTTPException(400, detail={
            "error": "missing_parameter",
            "message": "pass implementation_id (preferred), or feature + target_version"})
    conn = _conn()

    impl_id = implementation_id
    if not impl_id:
        feat = repo.resolve_feature(conn, feature)
        if feat is None:
            raise HTTPException(404, detail={"error": "unknown_feature", "message": feature})
        rows = repo.resolve_targets(conn, product, solver, target_version)
        tgt = _target_or_404(rows, product, solver, target_version)
        cands = repo.implementations(conn, feat["feature_id"], tgt["target_id"])
        if not cands:
            raise HTTPException(404, detail={"error": "no_implementation",
                                             "message": "no recorded implementation for this "
                                                        "feature/target"})
        impl_id = cands[0]["implementation_id"]

    impl = repo.implementation(conn, impl_id)
    if impl is None:
        raise HTTPException(404, detail={"error": "unknown_implementation",
                                         "message": implementation_id})

    doc = repo.document_ref(conn, impl["recipe_doc_id"]) if impl.get("recipe_doc_id") else None
    content, content_error = None, None
    if doc and _doc_fetcher is not None:
        try:
            fetched = _doc_fetcher(doc["doc_id"], doc["collection"])
            content = fetched.get("text") if fetched else None
            if not content:
                content_error = "document not found in retrieval index"
        except Exception as e:  # noqa: BLE001
            content_error = "retrieval error: %s" % type(e).__name__
    elif not doc:
        content_error = "no recipe_doc_id recorded for this implementation"

    return {
        "implementation": {
            "implementation_id": impl["implementation_id"],
            "feature": impl["feature_name"],
            "target": {"product": impl["product"], "solver": impl["solver"],
                       "version": impl["version_label"], "update": impl["update_label"],
                       "build": impl["build_number"]},
            "kind": impl["implementation_kind"],
            "equivalence": impl["equivalence"],
            "verification_level": impl["verification_level"],
            "status": impl["status"],
            "preconditions": impl["preconditions"],
            "assumptions": impl["assumptions"],
            "limitations": impl["limitations"],
            "contract": impl["contract_json"],
        },
        "document": ({"doc_id": doc["doc_id"], "collection": doc["collection"],
                      "title": doc["title"], "source_path": doc["source_path"]} if doc else None),
        "dependencies": repo.dependencies(conn, impl_id),
        "validation_runs": repo.validation_runs(conn, impl_id),
        "content": content,
        "content_chars": len(content or ""),
        "content_error": content_error,
    }


@router.get("/compat/capabilities")
def compat_capabilities(target_id: Optional[str] = None, product: Optional[str] = None,
                        solver: Optional[str] = None, target_version: Optional[str] = None,
                        symbols: Optional[str] = None,
                        authorization: Optional[str] = Header(None)):
    """Recorded capability snapshot for an exact target, with per-fact provenance."""
    _auth(authorization)
    conn = _conn()
    if target_id:
        tgt = repo.get_target(conn, target_id)
        if tgt is None:
            raise HTTPException(404, detail={"error": "unknown_target", "message": target_id})
    else:
        if not target_version:
            raise HTTPException(400, detail={"error": "missing_parameter",
                                             "message": "pass target_id or target_version"})
        tgt = _target_or_404(repo.resolve_targets(conn, product, solver, target_version),
                             product, solver, target_version)

    snaps = repo.snapshots(conn, tgt["target_id"])
    wanted = [s.strip() for s in (symbols or "").split(",") if s.strip()]
    out_snaps = []
    for s in snaps:
        items = repo.capability_items(conn, s["snapshot_id"], wanted or None)
        out_snaps.append({
            "snapshot_id": s["snapshot_id"],
            "captured_at": s["captured_at"],
            "capture_method": s["capture_method"],
            "files": {"commands": s["commands_file"], "environment": s["environment_file"],
                      "syntax_probes": s["syntax_probes_file"]},
            "sha256": {"commands": s["commands_sha256"], "snapshot": s["snapshot_sha256"]},
            "items": [{"symbol": i["symbol"], "symbol_type": i["symbol_type"],
                       "presence": i["presence"], "signature_status": i["signature_status"],
                       "evidence_method": i["evidence_method"], "details": i["details_json"],
                       "notes": i["notes"]} for i in items],
            "notes": s["notes"],
        })

    return {
        "target": {"target_id": tgt["target_id"], "product": tgt["product"],
                   "solver": tgt["solver"], "version": tgt["version_label"],
                   "update": tgt["update_label"], "build": tgt["build_number"],
                   "platform": tgt["platform"], "captured_at": tgt["captured_at"]},
        "snapshots": out_snaps,
        "snapshot_count": len(out_snaps),
        "note": ("No runtime snapshot captured for this target. Availability derived from "
                 "official documentation only; documented absence is not runtime absence."
                 if not out_snaps else "All facts carry evidence_method provenance."),
    }

"""Read-only repository helpers over compatibility.db (exact lookups, no fuzziness)."""
import sqlite3
from typing import Any, Dict, List, Optional


def _rows(cur) -> List[Dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def resolve_feature(conn: sqlite3.Connection, name: str) -> Optional[Dict[str, Any]]:
    name = (name or "").strip()
    if not name:
        return None
    row = conn.execute(
        "SELECT feature_id, canonical_name, feature_kind, description FROM features "
        "WHERE lower(canonical_name) = lower(?)", (name,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT f.feature_id, f.canonical_name, f.feature_kind, f.description "
            "FROM features f JOIN feature_aliases a ON a.feature_id = f.feature_id "
            "WHERE lower(a.alias) = lower(?) LIMIT 1", (name,)).fetchone()
    return dict(row) if row else None


def feature_aliases(conn: sqlite3.Connection, feature_id: str) -> List[str]:
    return [r[0] for r in conn.execute(
        "SELECT alias FROM feature_aliases WHERE feature_id = ? ORDER BY alias", (feature_id,))]


def resolve_targets(conn: sqlite3.Connection, product: Optional[str], solver: Optional[str],
                    version: Optional[str], update: Optional[str] = None) -> List[Dict[str, Any]]:
    """Exact product/solver/version match; never collapse an update into its major release."""
    sql = ("SELECT * FROM target_environments WHERE lower(version_label) = lower(?)")
    args: List[Any] = [version]
    if product:
        sql += " AND lower(product) = lower(?)"
        args.append(product)
    if solver:
        sql += " AND lower(solver) = lower(?)"
        args.append(solver)
    if update is not None:
        sql += " AND update_label = ?"
        args.append(update)
    sql += " ORDER BY update_label, build_number"
    return _rows(conn.execute(sql, args))


def get_target(conn: sqlite3.Connection, target_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM target_environments WHERE target_id = ?", (target_id,)).fetchone()
    return dict(row) if row else None


def availability(conn: sqlite3.Connection, feature_id: str, target_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT fa.*, es.title AS source_title, es.url AS source_url "
        "FROM feature_availability fa LEFT JOIN evidence_sources es ON es.source_id = fa.source_id "
        "WHERE fa.feature_id = ? AND fa.target_id = ?", (feature_id, target_id)).fetchone()
    return dict(row) if row else None


def implementations(conn: sqlite3.Connection, feature_id: str, target_id: str) -> List[Dict[str, Any]]:
    return _rows(conn.execute(
        "SELECT implementation_id, implementation_kind, equivalence, verification_level, status, "
        "recipe_doc_id, source_path, preconditions, assumptions, limitations, contract_json "
        "FROM implementations WHERE feature_id = ? AND target_id = ? "
        "ORDER BY CASE equivalence WHEN 'exact' THEN 0 WHEN 'domain_equivalent' THEN 1 "
        "WHEN 'approximate' THEN 2 WHEN 'partial' THEN 3 ELSE 4 END, verification_level DESC",
        (feature_id, target_id)))


def implementation(conn: sqlite3.Connection, implementation_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT i.*, f.canonical_name AS feature_name, t.product, t.solver, t.version_label, "
        "t.update_label, t.build_number FROM implementations i "
        "JOIN features f ON f.feature_id = i.feature_id "
        "JOIN target_environments t ON t.target_id = i.target_id "
        "WHERE i.implementation_id = ?", (implementation_id,)).fetchone()
    return dict(row) if row else None


def dependencies(conn: sqlite3.Connection, implementation_id: str) -> List[Dict[str, Any]]:
    return _rows(conn.execute(
        "SELECT dependency_name, dependency_type, required, target_presence "
        "FROM implementation_dependencies WHERE implementation_id = ? "
        "ORDER BY dependency_type, dependency_name", (implementation_id,)))


def validation_runs(conn: sqlite3.Connection, implementation_id: str) -> List[Dict[str, Any]]:
    return _rows(conn.execute(
        "SELECT validation_run_id, test_method, result, run_at, runner, report_path, notes "
        "FROM validation_runs WHERE implementation_id = ? ORDER BY run_at DESC", (implementation_id,)))


def document_ref(conn: sqlite3.Connection, doc_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT doc_id, collection, doc_type, title, source_path, qdrant_point_id, metadata_json "
        "FROM document_refs WHERE doc_id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def snapshots(conn: sqlite3.Connection, target_id: str) -> List[Dict[str, Any]]:
    return _rows(conn.execute(
        "SELECT * FROM capability_snapshots WHERE target_id = ? ORDER BY captured_at DESC",
        (target_id,)))


def capability_items(conn: sqlite3.Connection, snapshot_id: str,
                     symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if symbols:
        marks = ",".join("?" * len(symbols))
        return _rows(conn.execute(
            "SELECT * FROM capability_items WHERE snapshot_id = ? AND lower(symbol) IN (%s) "
            "ORDER BY symbol" % marks, [snapshot_id] + [s.lower() for s in symbols]))
    return _rows(conn.execute(
        "SELECT * FROM capability_items WHERE snapshot_id = ? ORDER BY symbol LIMIT 500",
        (snapshot_id,)))


def symbol_presence(conn: sqlite3.Connection, target_id: str, symbols: List[str]) -> Dict[str, str]:
    """Best-effort presence of symbols for a target, from any snapshot (newest first)."""
    out: Dict[str, str] = {}
    for snap in snapshots(conn, target_id):
        items = capability_items(conn, snap["snapshot_id"], symbols)
        for it in items:
            out.setdefault(it["symbol"].lower(), it["presence"])
    return out


def stats(conn: sqlite3.Connection) -> Dict[str, int]:
    out = {}
    for t in ("target_environments", "features", "feature_aliases", "evidence_sources",
              "document_refs", "capability_snapshots", "capability_items",
              "feature_availability", "implementations", "implementation_dependencies",
              "validation_runs"):
        out[t] = conn.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    return out

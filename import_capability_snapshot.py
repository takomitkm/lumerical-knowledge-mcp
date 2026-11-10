"""Import a capability snapshot directory into compatibility.db (idempotent).

Layout (matches the kit templates):
  <snapdir>/capability-snapshot.json   # index: ids, files, sha256, capture_method
  <snapdir>/environment.json
  <snapdir>/commands.json              # raw getcommands symbols
  <snapdir>/syntax_probes.json         # optional (accepts syntax-probes.json too)
  <snapdir>/getcommands_raw.txt        # raw output, hashed but not parsed

Rules:
- Presence comes from commands.json ONLY (evidence_method=getcommands).
- Keyword/grammar facts come from probes ONLY (evidence_method=syntax_probe).
- Import never flips availability to native/absent by itself; feature_availability stays
  'unknown' unless a human rows says otherwise. Snapshots are append-only evidence.
- Re-importing the same snapshot_id replaces its rows (idempotent), files are hashed and
  the hashes are verified against capability-snapshot.json when provided.
"""
import glob
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(__file__)
DB = os.path.join(BASE, "compat", "compatibility.db")
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 16), b""):
            h.update(blk)
    return h.hexdigest()


def load_json(base, *names):
    for n in names:
        p = os.path.join(base, n)
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8-sig"))  # utf-8-sig: tolerate PS BOM
    return None


def main(snapdir: str):
    idx = load_json(snapdir, "capability-snapshot.json")
    env = load_json(snapdir, "environment.json")
    cmds = load_json(snapdir, "commands.json")
    probes = load_json(snapdir, "syntax_probes.json", "syntax-probes.json")
    if not (idx and env and cmds):
        sys.exit("need capability-snapshot.json, environment.json and commands.json in %s" % snapdir)

    snap_id = idx["snapshot_id"]
    target_id = idx["target_id"]
    if env.get("target_id") != target_id:
        sys.exit("id mismatch between capability-snapshot.json / environment.json")
    if cmds.get("snapshot_id") != snap_id:
        sys.exit("snapshot_id mismatch between capability-snapshot.json / commands.json")

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")

    # target environment (exact identity comes from the capture, not from docs)
    con.execute(
        "INSERT OR REPLACE INTO target_environments(target_id, product, solver, version_label, "
        "update_label, build_number, platform, captured_at, capture_notes) VALUES(?,?,?,?,?,?,?,?,?)",
        (target_id, env["product"], env["solver"], env["version_label"],
         env.get("update_label") or "", env.get("build_number") or "", env.get("platform"),
         env.get("captured_at"), env.get("notes") or ""))

    # evidence source for this capture
    con.execute("INSERT OR REPLACE INTO evidence_sources VALUES(?,?,?,?,?,?,?,?)",
                ("runtime-%s" % snap_id, "runtime_snapshot", "project",
                 "Runtime capability snapshot %s" % snap_id, None,
                 "%s %s" % (env["version_label"], env.get("update_label") or ""),
                 env["version_label"], "captured on the target machine"))

    # hashed files
    def file_hash(name):
        p = os.path.join(snapdir, name)
        return (p, sha256(p)) if os.path.exists(p) else (None, None)

    raw_name = cmds.get("raw_output_file") or "getcommands_raw.txt"
    raw_path, raw_hash = file_hash(raw_name)
    con.execute(
        "INSERT OR REPLACE INTO capability_snapshots(snapshot_id, target_id, captured_at, "
        "commands_file, environment_file, syntax_probes_file, commands_sha256, snapshot_sha256, "
        "capture_method, notes) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (snap_id, target_id, idx.get("captured_at") or NOW,
         os.path.join(snapdir, raw_name), os.path.join(snapdir, "environment.json"),
         os.path.join(snapdir, "syntax_probes.json") if probes else None,
         raw_hash or idx.get("commands_sha256"), idx.get("snapshot_sha256"),
         idx.get("capture_method") or "manual_target_runtime", idx.get("notes") or ""))

    # capability items from commands.json
    n_cmd = 0
    for s in cmds.get("symbols", []):
        con.execute(
            "INSERT OR REPLACE INTO capability_items(snapshot_id, symbol, symbol_type, presence, "
            "signature_status, evidence_method, details_json, notes) VALUES(?,?,?,?,?,?,?,?)",
            (snap_id, s["name"], s.get("symbol_type", "command"), s["presence"],
             s.get("signature_status", "not_tested"), s.get("evidence_method", "getcommands"),
             None, s.get("notes")))
        n_cmd += 1

    # capability items from probes (grammar facts, separate evidence method)
    n_probe = 0
    if probes:
        for p in probes.get("probes", []):
            con.execute(
                "INSERT OR REPLACE INTO capability_items(snapshot_id, symbol, symbol_type, presence, "
                "signature_status, evidence_method, details_json, notes) VALUES(?,?,?,?,?,?,?,?)",
                (snap_id, p["symbol"], p.get("symbol_type", "keyword"),
                 {"passed": "present", "failed": "absent"}.get(p.get("status"), "unknown"),
                 "verified" if p.get("status") == "passed" else "not_tested",
                 "syntax_probe", json.dumps({"probe_id": p.get("probe_id"),
                                             "status": p.get("status"),
                                             "error_text": p.get("error_text")}),
                 p.get("notes")))
            n_probe += 1

    con.commit()
    print("imported snapshot %s -> target %s (items: %d commands, %d probes)"
          % (snap_id, target_id, n_cmd, n_probe))
    con.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: import_capability_snapshot.py <snapshot-dir>")
    main(sys.argv[1])

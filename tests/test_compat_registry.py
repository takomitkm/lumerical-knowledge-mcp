"""Phase 1 unit tests for the compatibility registry (no server, no network).

Run: python -m unittest discover -s tests -p "test_compat_*.py" -v
"""
import os
import sqlite3
import sys
import tempfile
import unittest

SHIM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shim")
sys.path.insert(0, SHIM)

from compat import db as cdb  # noqa: E402
from compat import repo  # noqa: E402


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="compat-test-")
        self.path = os.path.join(self.tmp, "compatibility.db")
        os.environ["COMPAT_DB"] = self.path
        # fresh thread-local connection per test
        cdb._local.__dict__.clear()
        self.conn = cdb.connect()
        self.info = cdb.init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        cdb._local.__dict__.clear()
        os.environ.pop("COMPAT_DB", None)

    # ---- schema / migration ----
    def test_schema_version_and_tables(self):
        self.assertEqual(self.info["schema_version"], "1")
        for t in ("target_environments", "features", "feature_aliases", "evidence_sources",
                  "document_refs", "capability_snapshots", "capability_items",
                  "feature_availability", "implementations", "implementation_dependencies",
                  "validation_runs", "schema_meta"):
            self.assertIn(t, self.info["tables"])

    def test_migration_is_idempotent(self):
        again = cdb.init_db(cdb.connect())
        self.assertEqual(again["schema_version"], "1")
        self.assertEqual(again["tables"], self.info["tables"])

    # ---- constraints ----
    def test_foreign_key_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO feature_availability(feature_id,target_id,status,evidence_basis,"
                "checked_at) VALUES('nope','nope-target','native','official_docs','2026-01-01')")

    def test_check_constraint_on_status(self):
        self.conn.execute("INSERT INTO target_environments VALUES"
                          "('t1','Lumerical','shared','2024 R1','','v241',NULL,NULL,'')")
        self.conn.execute("INSERT INTO features VALUES('f1','sort','command','')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO feature_availability(feature_id,target_id,status,evidence_basis,"
                "checked_at) VALUES('f1','t1','probably','official_docs','2026-01-01')")

    # ---- lookup semantics ----
    def _seed(self):
        c = self.conn
        c.execute("INSERT INTO target_environments VALUES"
                  "('t1','Lumerical','shared','2024 R1','','v241',NULL,NULL,'')")
        c.execute("INSERT INTO features VALUES('f1','sort','command','sort docs')")
        c.execute("INSERT INTO features VALUES('f2','median','command','median docs')")
        c.execute("INSERT INTO feature_aliases VALUES('sortrows','f1','legacy')")
        c.execute("INSERT INTO evidence_sources VALUES"
                  "('src1','official_command_doc','ansys','docs.json',NULL,'2024 R1','2024 R1','')")
        c.execute("INSERT INTO feature_availability(feature_id,target_id,status,evidence_basis,"
                  "source_id,checked_at) VALUES('f1','t1','native','official_docs','src1','2026-11-10')")
        c.commit()

    def test_resolve_feature_by_name_and_alias(self):
        self._seed()
        self.assertEqual(repo.resolve_feature(self.conn, "sort")["feature_id"], "f1")
        self.assertEqual(repo.resolve_feature(self.conn, "SORT")["feature_id"], "f1")
        self.assertEqual(repo.resolve_feature(self.conn, "sortrows")["feature_id"], "f1")
        self.assertIsNone(repo.resolve_feature(self.conn, "does_not_exist"))

    def test_unknown_availability_is_none_not_absent(self):
        self._seed()
        # feature exists, but no availability row -> must be None (=> API returns 'unknown')
        self.assertIsNone(repo.availability(self.conn, "f2", "t1"))
        self.assertEqual(repo.availability(self.conn, "f1", "t1")["status"], "native")

    def test_exact_version_matching_only(self):
        self._seed()
        self.assertEqual(len(repo.resolve_targets(self.conn, None, None, "2024 R1")), 1)
        self.assertEqual(len(repo.resolve_targets(self.conn, None, None, "2024 R2")), 0)
        self.assertEqual(len(repo.resolve_targets(self.conn, None, None, "v241")), 0)

    def test_implementations_ordered_by_equivalence(self):
        self._seed()
        for iid, eq in (("impl-a", "partial"), ("impl-b", "exact"), ("impl-c", "approximate")):
            self.conn.execute(
                "INSERT INTO implementations(implementation_id,feature_id,target_id,"
                "implementation_kind,equivalence,verification_level,status) "
                "VALUES(?,?,?,?,?,?,?)", (iid, "f1", "t1", "backport", eq, "L1", "static_checked"))
        self.conn.commit()
        order = [r["implementation_id"] for r in repo.implementations(self.conn, "f1", "t1")]
        self.assertEqual(order, ["impl-b", "impl-c", "impl-a"])

    def test_dependencies_and_stats(self):
        self._seed()
        self.conn.execute(
            "INSERT INTO implementations(implementation_id,feature_id,target_id,implementation_kind,"
            "equivalence,verification_level,status) VALUES('impl-x','f1','t1','backport','partial','L1','static_checked')")
        self.conn.execute("INSERT INTO implementation_dependencies(implementation_id,dependency_name,dependency_type," "required,target_presence,evidence_source_id) VALUES" "('impl-x','pinch','command',1,'present','src1')")
        self.conn.commit()
        deps = repo.dependencies(self.conn, "impl-x")
        self.assertEqual(deps[0]["dependency_name"], "pinch")
        self.assertEqual(deps[0]["target_presence"], "present")
        stats = repo.stats(self.conn)
        self.assertGreaterEqual(stats["features"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)


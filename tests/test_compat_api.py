"""API tests for the compat endpoints (in-process, no network, no server restart).

Uses FastAPI TestClient against a *fresh* app import with COMPAT_DB pointed at a temp copy
seeded with the kit's own data plus a small fixture target.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(ROOT, "shim")
sys.path.insert(0, SHIM)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="compat-api-")
        db = os.path.join(cls.tmp, "compatibility.db")
        shutil.copyfile(os.path.join(ROOT, "compat", "compatibility.db"), db)
        con = sqlite3.connect(db)
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("INSERT OR REPLACE INTO target_environments VALUES"
                    "('t-api','Lumerical','shared','2099 Z9','','v-test',NULL,NULL,'api fixture')")
        con.execute("INSERT OR REPLACE INTO features VALUES('f-api','sort','command','fixture')")
        con.commit()
        con.close()
        os.environ["COMPAT_DB"] = db
        # import app fresh with the temp db
        for m in list(sys.modules):
            if m == "app" or m.startswith("compat"):
                del sys.modules[m]
        import app as app_mod  # noqa: E402
        app_mod.app.dependency_overrides = {}
        from fastapi.testclient import TestClient  # noqa: E402
        cls.client = TestClient(app_mod.app)
        cls.token = os.environ.get("RAG_TEST_TOKEN", "test-token-please-ignore")
        app_mod.RAG_TOKEN = cls.token  # auth compares against module-level token
        cls.VERSION = "2099 Z9"  # unique fixture version: cannot collide with real targets

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.environ.pop("COMPAT_DB", None)

    def H(self, tok=None):
        h = {}
        if tok is not False:
            h["Authorization"] = "Bearer " + (tok if tok is not None else self.token)
        return h

    # ---- auth ----
    def test_requires_bearer(self):
        r = self.client.get("/compat/lookup", params={"feature": "sort", "target_version": self.VERSION})
        self.assertIn(r.status_code, (401, 403))
        r = self.client.get("/compat/lookup", params={"feature": "sort", "target_version": self.VERSION},
                            headers=self.H("wrong"))
        self.assertIn(r.status_code, (401, 403))

    # ---- validation / not found ----
    def test_missing_params_400(self):
        # feature alone is fine now (target_version optional), but NO target of any kind -> 400
        r = self.client.get("/compat/lookup", params={"feature": "sort"}, headers=self.H())
        self.assertEqual(r.status_code, 400)
        r = self.client.get("/compat/recipe", headers=self.H())
        self.assertEqual(r.status_code, 400)  # our own check (impl id vs feature+version)

    def test_unknown_feature_404(self):
        r = self.client.get("/compat/lookup",
                            params={"feature": "definitely_not_a_command", "target_version": self.VERSION},
                            headers=self.H())
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["error"], "unknown_feature")

    def test_unknown_target_404_with_hint(self):
        r = self.client.get("/compat/lookup",
                            params={"feature": "sort", "target_version": "1999 X1"}, headers=self.H())
        self.assertEqual(r.status_code, 404)
        d = r.json()["detail"]
        self.assertEqual(d["error"], "unknown_target_environment")
        self.assertIn("NOT proof", d["hint"])

    # ---- exact matching / unknown semantics ----
    def test_lookup_known_fixture(self):
        r = self.client.get("/compat/lookup",
                            params={"feature": "sort", "target_version": self.VERSION}, headers=self.H())
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["target"]["version"], self.VERSION)
        self.assertEqual(d["availability"]["status"], "unknown")  # fixture has no availability row
        self.assertIn("required_next_evidence", d)

    def test_capabilities_needs_target(self):
        r = self.client.get("/compat/capabilities", headers=self.H())
        self.assertEqual(r.status_code, 400)
        r = self.client.get("/compat/capabilities",
                            params={"target_version": self.VERSION}, headers=self.H())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["snapshot_count"], 0)

    def test_recipe_unknown_impl_404(self):
        r = self.client.get("/compat/recipe", params={"implementation_id": "nope.nope"},
                            headers=self.H())
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)




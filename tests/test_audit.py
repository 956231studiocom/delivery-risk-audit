"""Behavioural tests for the seven checks.

These assert the properties the README promises: deterministic file order,
stable grade boundaries, seven checks in every result, and the n/a escape
hatch for checks that do not apply.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import audit  # noqa: E402


class TestWalk(unittest.TestCase):
    def test_walk_order_is_deterministic(self):
        # Same repository must produce the same order on Windows and Linux,
        # otherwise sampled checks drift between machines.
        files, dirs = audit.walk(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertEqual(files, sorted(files))
        self.assertEqual(dirs, sorted(dirs))

    def test_walk_skips_vendor_directories(self):
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "node_modules", "left-pad"))
            with open(os.path.join(root, "node_modules", "left-pad", "index.js"), "w") as fh:
                fh.write("module.exports = 1\n")
            with open(os.path.join(root, "app.py"), "w") as fh:
                fh.write("print(1)\n")
            files, dirs = audit.walk(root)
            self.assertIn("app.py", files)
            self.assertFalse([f for f in files if "node_modules" in f])
        finally:
            shutil.rmtree(root)


class TestGrade(unittest.TestCase):
    def test_thresholds_are_inclusive(self):
        self.assertEqual(audit.grade(85), "Low")
        self.assertEqual(audit.grade(84.9), "Medium")
        self.assertEqual(audit.grade(70), "Medium")
        self.assertEqual(audit.grade(69.9), "High")
        self.assertEqual(audit.grade(50), "High")
        self.assertEqual(audit.grade(49.9), "Severe")
        self.assertEqual(audit.grade(0), "Severe")


class TestRun(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _write(self, rel, text):
        path = os.path.join(self.root, rel)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_always_returns_seven_checks_with_weights(self):
        self._write("app.py", "print(1)\n")
        r = audit.run(self.root, "fixture")
        self.assertEqual(len(r["checks"]), 7)
        self.assertEqual([c["id"] for c in r["checks"]], ["C1", "C2", "C3", "C4", "C5", "C6", "C7"])
        self.assertAlmostEqual(sum(c["weight"] for c in r["checks"]), 1.0, places=6)
        for c in r["checks"]:
            self.assertGreaterEqual(c["score"], 0)
            self.assertLessEqual(c["score"], 10)
            self.assertIsInstance(c["evidence"], list)

    def test_score_stays_in_range(self):
        self._write("app.py", "print(1)\n")
        r = audit.run(self.root, "fixture")
        self.assertGreaterEqual(r["total_score"], 0)
        self.assertLessEqual(r["total_score"], 100)
        self.assertIn(r["risk_level"], ("Low", "Medium", "High", "Severe"))

    def test_memory_check_is_na_without_agent_files(self):
        self._write("app.py", "print(1)\n")
        r = audit.run(self.root, "fixture")
        c4 = [c for c in r["checks"] if c["id"] == "C4"][0]
        self.assertTrue(c4.get("na"), "a plain script repo has no agent memory to audit")
        self.assertEqual(c4["score"], 10)

    def test_drift_is_zero_without_constraint_file(self):
        self._write("app.py", "print(1)\n")
        r = audit.run(self.root, "fixture")
        c3 = [c for c in r["checks"] if c["id"] == "C3"][0]
        self.assertEqual(c3["score"], 0)
        self.assertIn("none found", " ".join(c3["evidence"]))

    def test_constraint_file_with_prohibitions_raises_drift(self):
        self._write("app.py", "print(1)\n")
        self._write("AGENTS.md", "\n".join([
            "MUST NOT touch migrations.", "NEVER force push.", "DO NOT edit pricing.",
            "MUST NOT run rm -rf.", "NEVER bypass hooks.", "DO NOT change DNS.",
            "MUST keep tests green.", "MUST NOT delete fixtures.", "NEVER rewrite history.",
            "DO NOT merge without review.", "MUST NOT edit secrets.",
        ]))
        r = audit.run(self.root, "fixture")
        c3 = [c for c in r["checks"] if c["id"] == "C3"][0]
        self.assertGreaterEqual(c3["score"], 8)

    def test_test_directory_raises_false_green_score(self):
        self._write("app.py", "def add(a, b):\n    return a + b\n")
        for i in range(4):
            self._write("tests/test_app_%d.py" % i, "assert add(1, 2) == 3\n" * 8)
        r = audit.run(self.root, "fixture")
        c2 = [c for c in r["checks"] if c["id"] == "C2"][0]
        self.assertGreaterEqual(c2["score"], 5)
        self.assertTrue(any("test ratio" in e for e in c2["evidence"]))

    def test_markdown_report_has_every_check(self):
        self._write("app.py", "print(1)\n")
        md = audit.to_markdown(audit.run(self.root, "fixture"))
        for cid in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
            self.assertIn(cid, md)
        self.assertIn("Priority stack", md)


if __name__ == "__main__":
    unittest.main()

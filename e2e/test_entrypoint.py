"""End-to-end: run the Action entrypoint the way GitHub runs it.

This is the layer that catches false green. A unit test can pass while the
entrypoint writes nothing to GITHUB_STEP_SUMMARY and the run page stays blank.
So this test drives the real process and reads the real files.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ENTRY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "entrypoint.py")


def run_entry(point, summary, output, extra_env=None):
    env = dict(os.environ)
    env.update({
        "INPUT_PATH": point,
        "INPUT_NAME": "e2e-fixture",
        "INPUT_FAIL_UNDER": "",
        "INPUT_MARKDOWN": "true",
        "INPUT_REPORT_PATH": "report.md",
        "GITHUB_STEP_SUMMARY": summary,
        "GITHUB_OUTPUT": output,
    })
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, ENTRY], env=env, cwd=os.path.dirname(ENTRY),
                          capture_output=True, text=True, timeout=120)


class TestEntrypoint(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.target = os.path.join(self.work, "repo")
        os.makedirs(os.path.join(self.target, "tests"))
        with open(os.path.join(self.target, "app.py"), "w") as fh:
            fh.write("def f():\n    return 1\n")
        with open(os.path.join(self.target, "tests", "test_app.py"), "w") as fh:
            fh.write("assert f() == 1\n" * 6)
        self.summary = os.path.join(self.work, "summary.md")
        self.output = os.path.join(self.work, "out.txt")
        for p in (self.summary, self.output):
            open(p, "w").close()

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)
        for stray in ("audit-report.md", "audit-report.json"):
            p = os.path.join(os.path.dirname(ENTRY), stray)
            if os.path.exists(p):
                os.remove(p)

    def test_writes_summary_and_outputs(self):
        r = run_entry(self.target, self.summary, self.output)
        self.assertEqual(r.returncode, 0, r.stderr)

        with open(self.output, encoding="utf-8") as fh:
            out = fh.read()
        self.assertIn("score=", out)
        self.assertIn("grade=", out)
        self.assertIn("report=report.md", out)

        with open(self.summary, encoding="utf-8") as fh:
            summary = fh.read()
        # The run page must not be blank: table plus a link back to the product.
        self.assertIn("Scorecard", summary)
        self.assertIn("956231studio.com/ai-code-audit", summary)
        for cid in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
            self.assertIn(cid, summary)

    def test_report_and_json_are_written(self):
        r = run_entry(self.target, self.summary, self.output)
        self.assertEqual(r.returncode, 0, r.stderr)
        base = os.path.dirname(ENTRY)
        self.assertTrue(os.path.exists(os.path.join(base, "report.md")))
        with open(os.path.join(base, "audit-report.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertEqual(len(d["checks"]), 7)
        os.remove(os.path.join(base, "report.md"))

    def test_fail_under_flips_exit_code(self):
        r = run_entry(self.target, self.summary, self.output, {"INPUT_FAIL_UNDER": "101"})
        self.assertEqual(r.returncode, 1, "score can never reach 101, so the gate must fail")
        self.assertIn("below fail-under", r.stdout)

    def test_missing_path_fails_loudly(self):
        r = run_entry(os.path.join(self.work, "does-not-exist"), self.summary, self.output)
        self.assertEqual(r.returncode, 2)
        self.assertIn("::error::", r.stdout)

    def _read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_repeat_runs_are_stable(self):
        run_entry(self.target, self.summary, self.output)
        first = self._read(self.output)
        open(self.output, "w").close()
        run_entry(self.target, self.summary, self.output)
        second = self._read(self.output)
        self.assertEqual([l for l in first.splitlines() if l.startswith("score=")],
                         [l for l in second.splitlines() if l.startswith("score=")])


if __name__ == "__main__":
    unittest.main()

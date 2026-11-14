"""CLI-level tests: exit codes, output formats, python -m entry point."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from skill_ci.cli import main  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class CliTests(unittest.TestCase):
    def _target(self, *names):
        tmp = tempfile.mkdtemp(prefix="skillci-cli-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for name in names:
            shutil.copytree(FIXTURES / name, Path(tmp) / name)
        return tmp

    def test_exit_0_when_no_error_findings(self):
        target = self._target("good-sample")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main([target, "--format", "json"]), 0)

    def test_exit_1_when_error_findings(self):
        target = self._target("bad-name")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main([target]), 1)

    def test_exit_2_for_missing_target(self):
        self.assertEqual(main(["Z:/__no_such_dir_skillci__"]), 2)

    def test_markdown_report_goes_to_stdout(self):
        target = self._target("good-sample")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main([target])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("skill-lint report", out)
        self.assertIn("No findings", out)
        self.assertIn("Exit code: 0", out)

    def test_json_report_shape_and_exit_code(self):
        target = self._target("bad-name")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main([target, "--format", "json"])
        self.assertEqual(code, 1)
        payload = json.loads(buf.getvalue())
        self.assertIn("findings", payload)
        self.assertIn("summary", payload)
        self.assertEqual(payload["summary"]["exit_code"], 1)
        ids = {f["rule_id"] for f in payload["findings"]}
        self.assertIn("FM003", ids)

    def test_json_report_zero_exit_when_only_warnings(self):
        target = self._target("danger-skill")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main([target, "--format", "json"])
        self.assertEqual(code, 0)  # SEC findings are warnings, not errors
        payload = json.loads(buf.getvalue())
        ids = {f["rule_id"] for f in payload["findings"]}
        self.assertEqual(ids, {"SEC001", "SEC002", "SEC003"})
        for finding in payload["findings"]:
            for key in ("rule_id", "severity", "file", "line", "message"):
                self.assertIn(key, finding)

    @staticmethod
    def _env():
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        return env

    def test_python_m_entrypoint_help(self):
        proc = subprocess.run(
            [sys.executable, "-m", "skill_ci", "--help"],
            cwd=str(REPO_ROOT),
            env=self._env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("skill-lint", proc.stdout)

    def test_python_m_entrypoint_exit_codes(self):
        good = self._target("good-sample")
        proc = subprocess.run(
            [sys.executable, "-m", "skill_ci", good],
            cwd=str(REPO_ROOT),
            env=self._env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("No findings", proc.stdout)
        bad = self._target("bad-name")
        proc = subprocess.run(
            [sys.executable, "-m", "skill_ci", bad, "--format", "json"],
            cwd=str(REPO_ROOT),
            env=self._env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["summary"]["exit_code"], 1)


if __name__ == "__main__":
    unittest.main()

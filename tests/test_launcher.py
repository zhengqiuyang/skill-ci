"""Launcher tests: bin/skill-lint (sh) and bin/skill-lint.cmd (cmd.exe).

The launchers must (a) derive the repo root from the script location,
(b) work from any cwd, (c) survive paths containing spaces, (d) install
nothing. The sh root derivation is exercised with a real subprocess run
per the W2 plan ("subprocess 真跑"), including its failure path when no
src/skill_ci exists next to the script.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_SH = REPO_ROOT / "bin" / "skill-lint"
BIN_CMD = REPO_ROOT / "bin" / "skill-lint.cmd"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

BASH = shutil.which("bash")


def _copy_fixture(name: str, dest: Path) -> Path:
    target = dest / name
    shutil.copytree(FIXTURES / name, target)
    return target


@unittest.skipIf(BASH is None, "bash not available on PATH")
class ShLauncherTests(unittest.TestCase):
    def _run(self, args, cwd):
        return subprocess.run(
            [BASH, str(BIN_SH), *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_run_from_unrelated_cwd_json(self):
        """Bare `bin/skill-lint <target>` from a foreign cwd finds sources."""
        tmp = Path(tempfile.mkdtemp(prefix="skillci-bin-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        target = _copy_fixture("bad-name", tmp)
        proc = self._run([str(target), "--format", "json"], cwd=tmp.parent)
        self.assertEqual(proc.returncode, 1, proc.stderr)  # bad-name -> FM003 error
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["summary"]["exit_code"], 1)
        self.assertEqual(payload["skills_scanned"], 1)

    def test_target_with_spaces(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci bin spaces-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        target = _copy_fixture("good-sample", tmp)
        proc = self._run([str(target)], cwd=tmp.parent)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("No findings", proc.stdout)

    def test_help_passes_through(self):
        proc = self._run(["--help"], cwd=tempfile.gettempdir())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("skill-lint", proc.stdout)

    def test_missing_sources_next_to_script_fails_loudly(self):
        """Root derivation: script copied away from the repo must exit 2."""
        tmp = Path(tempfile.mkdtemp(prefix="skillci-bin-orphan-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        orphan = tmp / "bin"
        orphan.mkdir()
        shutil.copy(BIN_SH, orphan / "skill-lint")
        proc = subprocess.run(
            [BASH, str(orphan / "skill-lint"), str(tmp)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("cannot locate", proc.stderr)

    def test_launcher_script_is_lf_only(self):
        """A CRLF-poisoned sh launcher would break on POSIX shells."""
        data = BIN_SH.read_bytes()
        self.assertNotIn(b"\r\n", data)


@unittest.skipIf(os.name != "nt", "cmd.exe launcher is Windows-only")
class CmdLauncherTests(unittest.TestCase):
    def _run(self, args):
        # cmd.exe argument passing needs a single quoted string; paths with
        # spaces survive because both launcher and target are quoted.
        quoted = " ".join(f'"{a}"' if " " in a else a for a in args)
        return subprocess.run(
            f'"{BIN_CMD}" {quoted}', shell=True, capture_output=True, text=True, timeout=60
        )

    def test_run_from_unrelated_cwd_json(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci-cmd-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        target = _copy_fixture("bad-name", tmp)
        proc = self._run([str(target), "--format", "json"])
        self.assertEqual(proc.returncode, 1, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["summary"]["exit_code"], 1)

    def test_target_with_spaces(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci cmd spaces-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        target = _copy_fixture("good-sample", tmp)
        proc = self._run([str(target)])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("No findings", proc.stdout)


if __name__ == "__main__":
    unittest.main()

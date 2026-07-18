from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PublicCliContractTest(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_build_version_uses_project_version_once(self) -> None:
        result = self.run_cli("build.py", "--version")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "Maple Mono Builder v7.9")
        self.assertEqual(result.stderr, "")

    def test_task_help_lists_all_public_commands(self) -> None:
        result = self.run_cli("task.py", "--help")

        self.assertEqual(result.returncode, 0)
        for command in ("nf", "fea", "release", "page", "cjk", "publish", "merge"):
            self.assertIn(command, result.stdout)

    def test_invalid_build_argument_returns_argparse_error(self) -> None:
        result = self.run_cli("build.py", "--unknown-option")

        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments: --unknown-option", result.stderr)


if __name__ == "__main__":
    unittest.main()

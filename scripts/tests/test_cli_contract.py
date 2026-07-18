from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.config import cli
from scripts.pipeline import main as run_build_cli


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PublicCliContractTest(unittest.TestCase):
    def run_cli(
        self,
        *args: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_build_version_uses_project_version_once(self) -> None:
        result = self.run_cli("build.py", "--version")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "Maple Mono Builder v7.9")
        self.assertEqual(result.stderr, "")

    def test_task_help_lists_all_public_commands(self) -> None:
        result = self.run_cli("task.py", "--help")

        self.assertEqual(result.returncode, 0)
        for command in ("nf", "fea", "release", "page", "cjk", "publish"):
            self.assertIn(command, result.stdout)

    def test_invalid_build_argument_returns_argparse_error(self) -> None:
        result = self.run_cli("build.py", "--unknown-option")

        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments: --unknown-option", result.stderr)

    def test_ci_dry_run_keeps_json_on_stdout_and_logs_warning_to_stderr(self) -> None:
        result = self.run_cli(
            "build.py",
            "--dry",
            "--ttf-only",
            extra_env={"GITHUB_ACTIONS": "true"},
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["behavior"]["formats"], ["ttf"])
        self.assertEqual(
            result.stderr,
            "[WARNING] [system] --ttf-only is deprecated; use --format ttf instead\n",
        )

    def test_log_level_can_suppress_warnings_without_changing_dry_run_json(
        self,
    ) -> None:
        result = self.run_cli(
            "build.py",
            "--dry",
            "--ttf-only",
            extra_env={"GITHUB_ACTIONS": "true", "MAPLE_LOG_LEVEL": "ERROR"},
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["behavior"]["formats"], ["ttf"])
        self.assertEqual(result.stderr, "")

    def test_pipeline_owns_cli_execution(self) -> None:
        self.assertFalse(hasattr(cli, "main"))

        with (
            patch("scripts.pipeline.configure_logging"),
            patch("scripts.pipeline.run") as run_pipeline,
        ):
            run_build_cli(["--dry"], version="v7.9")

        parsed_args = run_pipeline.call_args.args[0]
        self.assertTrue(parsed_args.dry)
        self.assertEqual(run_pipeline.call_args.kwargs["version"], "v7.9")


if __name__ == "__main__":
    unittest.main()

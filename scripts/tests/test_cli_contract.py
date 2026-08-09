from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.config import cli
from scripts.config.cli import parse_args
from scripts.pipeline import main as run_build_cli

PROJECT_ROOT = Path(__file__).resolve().parents[2]


BUILD_OPTION_CONTRACT = {
    ("-h", "--help"),
    ("-v", "--version"),
    ("-d", "--dry"),
    ("--debug",),
    ("-n", "--normal"),
    ("--standard-zero",),
    ("--feat",),
    ("--apply-fea-file",),
    ("--hinted",),
    ("--no-hinted",),
    ("--liga",),
    ("--no-liga",),
    ("--infinite-arrow",),
    ("--remove-tag-liga",),
    ("--line-height",),
    ("--width",),
    ("--format",),
    ("--ttf-only",),
    ("--least-styles",),
    ("--cache",),
    ("--archive",),
    ("--nf", "--nerd-font"),
    ("--no-nf", "--no-nerd-font"),
    ("--nf-mono",),
    ("--nf-propo",),
    ("--nf-variable",),
    ("--font-patcher",),
    ("--cjk",),
    ("--cjk-variable",),
    ("--cjk-narrow",),
    ("--cjk-scale-factor",),
    ("--cjk-hinted",),
    ("--no-cjk-hinted",),
    ("--cjk-both",),
    ("--cn",),
    ("--no-cn",),
    ("--cn-narrow",),
    ("--cn-scale-factor",),
    ("--cn-both",),
    ("--cn-rebuild",),
}


VALID_BUILD_OPTION_CASES = (
    (["--dry"], "dry", True),
    (["--debug"], "debug", True),
    (["--normal"], "normal", True),
    (["--standard-zero"], "standard_zero", True),
    (["--feat", "zero,cv01"], "feat", ["zero", "cv01"]),
    (["--apply-fea-file"], "apply_fea_file", True),
    (["--hinted"], "hinted", True),
    (["--no-hinted"], "hinted", False),
    (["--liga"], "liga", True),
    (["--no-liga"], "liga", False),
    (["--infinite-arrow"], "infinite_arrow", True),
    (["--remove-tag-liga"], "remove_tag_liga", True),
    (["--line-height", "1.2"], "line_height", 1.2),
    (["--width", "slim"], "width", "slim"),
    (["--format", "ttf,woff2"], "formats", ["ttf", "woff2"]),
    (["--ttf-only"], "ttf_only", True),
    (["--least-styles"], "least_styles", True),
    (["--cache"], "cache", True),
    (["--archive"], "archive", True),
    (["--nf"], "nerd_font", True),
    (["--no-nf"], "nerd_font", False),
    (["--nf-mono"], "nf_mono", True),
    (["--nf-propo"], "nf_propo", True),
    (["--nf-variable"], "nf_variable", True),
    (["--font-patcher"], "font_patcher", True),
    (["--cjk", "cn,jp", "--cjk", "kr"], "cjk", ["cn,jp", "kr"]),
    (["--cjk-variable"], "cjk_variable", True),
    (["--cjk-narrow"], "cjk_narrow", True),
    (["--cjk-scale-factor", "1.1,0.9"], "cjk_scale_factor", (1.1, 0.9)),
    (["--cjk-hinted"], "cjk_hinted", True),
    (["--no-cjk-hinted"], "cjk_hinted", False),
    (["--cjk-both"], "cjk_both", True),
    (["--cn"], "cn", True),
    (["--no-cn"], "cn", False),
    (["--cn-narrow"], "cn_narrow", True),
    (["--cn-scale-factor", "1.1"], "cn_scale_factor", (1.1, 1.1)),
    (["--cn-both"], "cn_both", True),
    (["--cn-rebuild"], "cn_rebuild", True),
)


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

    def test_build_help_short_and_long_options_are_equivalent(self) -> None:
        long_help = self.run_cli("build.py", "--help")
        short_help = self.run_cli("build.py", "-h")

        self.assertEqual(long_help.returncode, 0)
        self.assertEqual(short_help.returncode, 0)
        self.assertEqual(short_help.stdout, long_help.stdout)
        self.assertIn("Feature Options:", long_help.stdout)
        self.assertIn("Build Options:", long_help.stdout)
        self.assertIn("CJK Options:", long_help.stdout)
        self.assertEqual(long_help.stderr, "")
        self.assertEqual(short_help.stderr, "")

    def test_build_option_surface_matches_the_explicit_contract(self) -> None:
        option_surface = {
            tuple(action.option_strings)
            for action in cli.build_parser(version="v7.9")._actions
            if action.option_strings
        }

        self.assertEqual(option_surface, BUILD_OPTION_CONTRACT)

    def test_every_build_option_accepts_a_representative_value(self) -> None:
        for args, attribute, expected in VALID_BUILD_OPTION_CASES:
            with self.subTest(args=args):
                parsed = parse_args(args, version="v7.9")

                self.assertEqual(getattr(parsed, attribute), expected)

    def test_build_option_aliases_are_equivalent(self) -> None:
        aliases = (
            (["-d"], ["--dry"], "dry"),
            (["-n"], ["--normal"], "normal"),
            (["--nerd-font"], ["--nf"], "nerd_font"),
            (["--no-nerd-font"], ["--no-nf"], "nerd_font"),
        )
        for alias, canonical, attribute in aliases:
            with self.subTest(alias=alias):
                alias_value = getattr(parse_args(alias), attribute)
                canonical_value = getattr(parse_args(canonical), attribute)

                self.assertEqual(alias_value, canonical_value)

    def test_invalid_or_conflicting_build_options_fail_as_usage_errors(self) -> None:
        cases = (
            ["--width", "wide"],
            ["--format", "zip"],
            ["--cjk-variable", "woff2"],
            ["--cjk-scale-factor", "1,2,3"],
            ["--hinted", "--no-hinted"],
            ["--liga", "--no-liga"],
            ["--nf", "--no-nf"],
            ["--cn", "--no-cn"],
        )
        for args in cases:
            with self.subTest(args=args):
                with (
                    redirect_stderr(StringIO()),
                    self.assertRaises(SystemExit) as error,
                ):
                    parse_args(args)

                self.assertEqual(error.exception.code, 2)

    def test_task_help_lists_all_public_commands(self) -> None:
        result = self.run_cli("task.py", "--help")

        self.assertEqual(result.returncode, 0)
        for command in (
            "nf",
            "fea",
            "designspace",
            "release",
            "page",
            "cjk",
            "publish",
        ):
            self.assertIn(command, result.stdout)

    def test_page_command_contract_is_unchanged(self) -> None:
        result = self.run_cli("task.py", "page", "--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: task.py page [-h] [--woff2] [--sync]", result.stdout)
        self.assertIn("--woff2", result.stdout)
        self.assertIn("--sync", result.stdout)

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

        resolver = MagicMock()
        font_config = MagicMock()
        font_config.to_dict.return_value = {}
        runtime_context = MagicMock()
        runtime_context.to_dict.return_value = {}
        resolver.resolve.return_value = font_config
        resolver_factory = MagicMock(return_value=resolver)
        with (
            patch("scripts.pipeline.orchestrator.configure_logging"),
            patch("builtins.print"),
            patch(
                "scripts.pipeline.orchestrator.BuildConfigResolver", resolver_factory
            ),
            patch(
                "scripts.pipeline.orchestrator.BuildRuntimeContext.from_config",
                return_value=runtime_context,
            ),
        ):
            run_build_cli(["--dry"], version="v7.9")

        self.assertTrue(resolver.resolve.call_args.args[0].dry)
        self.assertEqual(
            resolver_factory.call_args.kwargs,
            {"version_tag": "v7.9"},
        )

    def test_debug_build_enables_debug_logging_for_the_cli_lifetime(self) -> None:
        observed_levels: list[str | None] = []
        resolver = MagicMock()
        font_config = MagicMock()
        font_config.to_dict.return_value = {}
        runtime_context = MagicMock()
        runtime_context.to_dict.return_value = {}
        resolver.resolve.side_effect = lambda _args: (
            observed_levels.append(os.environ.get("MAPLE_LOG_LEVEL")) or font_config
        )
        resolver_factory = MagicMock(return_value=resolver)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("scripts.pipeline.orchestrator.configure_logging"),
            patch("builtins.print"),
            patch(
                "scripts.pipeline.orchestrator.BuildConfigResolver",
                resolver_factory,
            ),
            patch(
                "scripts.pipeline.orchestrator.BuildRuntimeContext.from_config",
                return_value=runtime_context,
            ),
        ):
            run_build_cli(["--debug", "--dry"], version="v7.9")
            self.assertNotIn("MAPLE_LOG_LEVEL", os.environ)

        self.assertEqual(observed_levels, ["DEBUG"])

    def test_explicit_log_level_overrides_debug_default(self) -> None:
        observed_levels: list[str | None] = []
        resolver = MagicMock()
        font_config = MagicMock()
        font_config.to_dict.return_value = {}
        runtime_context = MagicMock()
        runtime_context.to_dict.return_value = {}
        resolver.resolve.side_effect = lambda _args: (
            observed_levels.append(os.environ.get("MAPLE_LOG_LEVEL")) or font_config
        )
        resolver_factory = MagicMock(return_value=resolver)
        with (
            patch.dict(os.environ, {"MAPLE_LOG_LEVEL": "ERROR"}, clear=True),
            patch("scripts.pipeline.orchestrator.configure_logging"),
            patch("builtins.print"),
            patch(
                "scripts.pipeline.orchestrator.BuildConfigResolver",
                resolver_factory,
            ),
            patch(
                "scripts.pipeline.orchestrator.BuildRuntimeContext.from_config",
                return_value=runtime_context,
            ),
        ):
            run_build_cli(["--debug", "--dry"], version="v7.9")

        self.assertEqual(observed_levels, ["ERROR"])


if __name__ == "__main__":
    unittest.main()

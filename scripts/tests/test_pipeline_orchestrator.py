from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.config.cli import parse_args
from scripts.config.resolver import BuildConfigResolver
from scripts.pipeline.orchestrator import BuildPlan


class BuildPlanResolutionTest(unittest.TestCase):
    def resolve_plan(
        self,
        args: list[str],
        config_data: dict | None = None,
    ) -> BuildPlan:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_text(
                json.dumps(config_data or {}),
                encoding="utf-8",
            )
            config = BuildConfigResolver(project_root=root).resolve(parse_args(args))
            return BuildPlan.from_config(config)

    def test_cli_and_config_resolve_to_expected_build_plans(self) -> None:
        cases = (
            (
                ["--debug"],
                {},
                BuildPlan(
                    target_styles=["Regular", "Italic"],
                    required_base_formats=("variable", "ttf"),
                    build_woff2=False,
                    build_nerd_font=False,
                    build_nerd_font_variable=False,
                    cjk_mode=None,
                    cleanup_base_static=False,
                    archive=False,
                ),
            ),
            (
                ["--format", "woff2", "--no-nf", "--no-hinted"],
                {},
                BuildPlan(
                    target_styles=None,
                    required_base_formats=("variable", "ttf"),
                    build_woff2=True,
                    build_nerd_font=False,
                    build_nerd_font_variable=False,
                    cjk_mode=None,
                    cleanup_base_static=True,
                    archive=False,
                ),
            ),
            (
                ["--no-nf", "--no-hinted", "--archive"],
                {"formats": ["otf"]},
                BuildPlan(
                    target_styles=None,
                    required_base_formats=("variable", "otf"),
                    build_woff2=False,
                    build_nerd_font=False,
                    build_nerd_font_variable=False,
                    cjk_mode=None,
                    cleanup_base_static=True,
                    archive=True,
                ),
            ),
            (
                ["--format", "ttf", "--least-styles", "--no-nf"],
                {},
                BuildPlan(
                    target_styles=["Regular", "Bold", "Italic", "BoldItalic"],
                    required_base_formats=("variable", "ttf"),
                    build_woff2=False,
                    build_nerd_font=False,
                    build_nerd_font_variable=False,
                    cjk_mode=None,
                    cleanup_base_static=False,
                    archive=False,
                ),
            ),
            (
                ["--cjk", "jp", "--cjk-variable", "--no-nf"],
                {"formats": ["otf"]},
                BuildPlan(
                    target_styles=None,
                    required_base_formats=("variable", "otf"),
                    build_woff2=False,
                    build_nerd_font=False,
                    build_nerd_font_variable=False,
                    cjk_mode="variable",
                    cleanup_base_static=True,
                    archive=False,
                ),
            ),
        )
        for args, config_data, expected in cases:
            with self.subTest(args=args, config_data=config_data):
                plan = self.resolve_plan(args, config_data)

                self.assertEqual(plan, expected)

        variable_plan = self.resolve_plan(
            ["--nf-variable", "--no-hinted", "--format", "otf"]
        )
        self.assertFalse(variable_plan.build_nerd_font)
        self.assertTrue(variable_plan.build_nerd_font_variable)
        self.assertEqual(variable_plan.required_base_formats, ("variable", "otf"))


if __name__ == "__main__":
    unittest.main()

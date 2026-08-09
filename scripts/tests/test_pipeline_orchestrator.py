from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

from scripts.config.cli import parse_args
from scripts.config.resolver import BuildConfigResolver
from scripts.pipeline.base_fonts import build_base_fonts, build_woff2_fonts
from scripts.pipeline.fontmake import (
    FontmakeBuildContext,
)
from scripts.pipeline.orchestrator import BuildPlan, MapleBuildPipeline
from scripts.tests.pipeline_fixtures import (
    make_builtin_entry,
    make_font_config,
    make_runtime_context,
)

if TYPE_CHECKING:
    from concurrent.futures import Executor


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


class MapleBuildPipelineDecisionTreeTest(unittest.TestCase):
    def test_build_runs_full_static_branch_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.archive = True
            font_config.behavior.formats = ["woff2"]
            font_config.cjk.entries = [make_builtin_entry("cn")]
            runtime_context = make_runtime_context(Path(tmp))
            events: list[str] = []
            fontmake_context = FontmakeBuildContext(
                Path(tmp) / "fonts" / "temp",
                Path(tmp) / "fonts" / "temp" / "variable",
                Path(tmp) / "fonts" / "temp" / "ttf",
                Path(tmp) / "fonts" / "temp" / "otf",
                (),
            )

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            with (
                patch.object(
                    MapleBuildPipeline,
                    "prepare_output_root",
                    side_effect=lambda: events.append("output-root"),
                ),
                patch.object(
                    MapleBuildPipeline,
                    "start_build_timer",
                    side_effect=lambda: events.append("start"),
                ),
                patch.object(
                    MapleBuildPipeline,
                    "write_build_config",
                    side_effect=lambda: events.append("config"),
                ),
                patch.object(
                    MapleBuildPipeline,
                    "write_build_record",
                    side_effect=lambda: events.append("record"),
                ),
                patch.object(MapleBuildPipeline, "_mark_stage_rebuilt"),
                patch.object(
                    MapleBuildPipeline,
                    "archive_outputs",
                    side_effect=lambda: events.append("archive"),
                ),
                patch.object(
                    MapleBuildPipeline,
                    "finish_build",
                    side_effect=lambda: events.append("finish"),
                ),
                patch(
                    "scripts.pipeline.orchestrator.build_woff2_fonts",
                    side_effect=lambda *_: events.append("woff2"),
                ),
                patch(
                    "scripts.pipeline.orchestrator.prepare_fontmake_sources",
                    side_effect=lambda *_: events.append("prepare") or fontmake_context,
                ),
                patch(
                    "scripts.pipeline.orchestrator.compile_fontmake_formats",
                    side_effect=lambda *_args, **_kwargs: events.append("compile"),
                ),
                patch(
                    "scripts.pipeline.orchestrator.build_variable_fonts",
                    side_effect=lambda *_: events.append("variable"),
                ),
                patch(
                    "scripts.pipeline.orchestrator.build_static_fonts",
                    side_effect=lambda *_args: events.append(_args[3]),
                ),
                patch(
                    "scripts.pipeline.orchestrator.build_base_fonts",
                    side_effect=lambda *_: events.append("ttf-autohint"),
                ),
                patch(
                    "scripts.pipeline.orchestrator.build_nerd_fonts",
                    side_effect=lambda *_: events.append("nf"),
                ),
                patch(
                    "scripts.pipeline.orchestrator.build_cjk_extended_static_outputs",
                    side_effect=lambda *_args, **_kwargs: events.append("cjk-static"),
                ),
                patch(
                    "scripts.pipeline.orchestrator.cleanup_unselected_base_formats",
                    side_effect=lambda *_: events.append("cleanup"),
                ),
            ):
                pipeline.build()

            self.assertEqual(
                events,
                [
                    "start",
                    "output-root",
                    "config",
                    "prepare",
                    "compile",
                    "variable",
                    "ttf",
                    "ttf-autohint",
                    "woff2",
                    "nf",
                    "cjk-static",
                    "cleanup",
                    "record",
                    "archive",
                    "finish",
                ],
            )

    def test_failed_fontmake_batch_cleans_prepared_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_path = Path(tmp) / "fonts" / "temp"
            font_config = make_font_config()
            runtime_context = make_runtime_context(Path(tmp))
            context = FontmakeBuildContext(
                temp_path,
                temp_path / "variable",
                temp_path / "ttf",
                temp_path / "otf",
                (),
            )
            pipeline = MapleBuildPipeline(font_config, runtime_context)

            with (
                patch.object(MapleBuildPipeline, "start_build_timer"),
                patch.object(MapleBuildPipeline, "prepare_output_root"),
                patch(
                    "scripts.pipeline.orchestrator.prepare_fontmake_sources",
                    return_value=context,
                ),
                patch(
                    "scripts.pipeline.orchestrator.compile_fontmake_formats",
                    side_effect=RuntimeError("compile failed"),
                ),
                patch("scripts.pipeline.orchestrator.shutil.rmtree") as rmtree,
                self.assertRaisesRegex(RuntimeError, "compile failed"),
            ):
                pipeline.build()

            rmtree.assert_called_once_with(temp_path, ignore_errors=True)
            self.assertTrue(
                (Path(runtime_context.output_root) / "build-config.json").is_file()
            )
            self.assertFalse(
                (Path(runtime_context.output_root) / "build-cache.json").exists()
            )

    def test_woff2_stage_uses_static_ttf_outputs_and_skips_debug_builds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            font_config.behavior.formats = ["woff2"]
            pipeline = MapleBuildPipeline(font_config, runtime_context)

            output_ttf = Path(runtime_context.output_ttf)
            output_ttf.mkdir(parents=True)
            (output_ttf / "MapleMono-Regular.ttf").touch()

            executor = cast("Executor", MagicMock())
            with patch("scripts.pipeline.base_fonts.convert_to_web") as convert:
                build_woff2_fonts(
                    [output_ttf / "MapleMono-Regular.ttf"],
                    runtime_context,
                    executor,
                )

            convert.assert_called_once_with(
                [output_ttf / "MapleMono-Regular.ttf"],
                output_dir=runtime_context.output_woff2,
                flavor="woff2",
                executor=executor,
            )
            self.assertTrue(pipeline.should_build_woff2_outputs())

            font_config.behavior.debug = True
            self.assertFalse(pipeline.should_build_woff2_outputs())

    def test_derived_stages_receive_only_current_build_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            font_config.behavior.formats = ["woff2"]
            font_config.behavior.least_styles = True
            pipeline = MapleBuildPipeline(font_config, runtime_context)
            raw_paths = pipeline._base_stage_expected_paths("ttf")
            hinted_paths = pipeline._base_stage_expected_paths("ttf-autohint")

            stale_path = Path(runtime_context.output_ttf) / "OldFamily-Regular.ttf"
            stale_path.parent.mkdir(parents=True)
            stale_path.touch()

            executor = cast("Executor", MagicMock())
            with (
                patch(
                    "scripts.pipeline.orchestrator.build_base_fonts",
                    return_value=hinted_paths,
                ) as auto_hint,
                patch.object(pipeline, "_mark_stage_rebuilt"),
                patch("scripts.pipeline.orchestrator.build_woff2_fonts") as convert,
                patch("scripts.pipeline.orchestrator.build_nerd_fonts") as build_nf,
            ):
                pipeline._build_derived_outputs(("ttf",), executor)

            auto_hint.assert_called_once_with(
                font_config,
                runtime_context,
                raw_paths,
                executor,
            )
            convert.assert_called_once_with(raw_paths, runtime_context, executor)
            build_nf.assert_called_once_with(
                font_config,
                runtime_context,
                hinted_paths,
                executor,
            )
            self.assertEqual(
                [path.name for path in raw_paths],
                [
                    "MapleMono-Regular.ttf",
                    "MapleMono-Bold.ttf",
                    "MapleMono-Italic.ttf",
                    "MapleMono-BoldItalic.ttf",
                ],
            )
            self.assertTrue(stale_path.is_file())

    def test_start_uses_a_human_readable_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            for width, width_summary in (
                ("default", None),
                ("narrow", "Width: narrow (600 -> 550, suffix NR)"),
                ("slim", "Width: slim (600 -> 500, suffix SL)"),
            ):
                font_config = make_font_config()
                font_config.feature.width = width
                pipeline = MapleBuildPipeline(font_config, runtime_context)

                with patch("scripts.pipeline.orchestrator.logger.info") as log_info:
                    pipeline.start_build_timer()

                log_info.assert_called_once()
                message = log_info.call_args.args[0] % log_info.call_args.args[1:]
                self.assertTrue(message.startswith("Maple Mono 7.900"))
                self.assertIn("  Formats: TTF, OTF, WOFF2\n  Styles: all", message)
                self.assertIn("  Options: hinting, ligatures", message)
                self.assertIn("  CJK: off\n  Cache: off", message)
                if width_summary is None:
                    self.assertNotIn("Width:", message)
                else:
                    self.assertIn(width_summary, message)


class DerivedOutputValidationTest(unittest.TestCase):
    def test_autohint_missing_input_fails_before_parallel_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            missing = Path(runtime_context.output_ttf) / "MapleMono-Regular.ttf"
            executor = cast("Executor", MagicMock())

            with (
                patch("scripts.pipeline.base_fonts.run_process_jobs") as run_jobs,
                self.assertRaisesRegex(
                    FileNotFoundError,
                    "Missing TTF auto-hint input files",
                ),
            ):
                build_base_fonts(
                    font_config,
                    runtime_context,
                    [missing],
                    executor,
                )

            run_jobs.assert_not_called()

    def test_autohint_rejects_colliding_outputs_before_parallel_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_context = make_runtime_context(tmp_path)
            font_config = make_font_config()
            current = Path(runtime_context.output_ttf) / "MapleMono-Regular.ttf"
            stale = tmp_path / "stale" / "MapleMono-Regular.ttf"
            current.parent.mkdir(parents=True)
            stale.parent.mkdir()
            current.touch()
            stale.touch()
            executor = cast("Executor", MagicMock())

            with (
                patch("scripts.pipeline.base_fonts.run_process_jobs") as run_jobs,
                self.assertRaisesRegex(
                    ValueError,
                    "Duplicate TTF auto-hint output paths",
                ),
            ):
                build_base_fonts(
                    font_config,
                    runtime_context,
                    [current, stale],
                    executor,
                )

            run_jobs.assert_not_called()
            self.assertTrue(stale.is_file())


class ArchiveOutputTest(unittest.TestCase):
    def test_archives_only_sorted_output_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            output_root = Path(runtime_context.output_dir)
            output_root.mkdir(parents=True)
            for name in ("Variable", "TTF", ".cjk-temp", "temp", "archive"):
                (output_root / name).mkdir()
            for name in ("build-config.json", "issue.fea"):
                (output_root / name).touch()

            pipeline = MapleBuildPipeline(make_font_config(), runtime_context)
            with patch(
                "scripts.pipeline.orchestrator.archive_fonts",
                return_value=("", "archive"),
            ) as archive_fonts:
                pipeline.archive_outputs()

            self.assertEqual(
                [
                    Path(call.kwargs["source_file_or_dir_path"]).name
                    for call in archive_fonts.call_args_list
                ],
                ["TTF", "Variable"],
            )


if __name__ == "__main__":
    unittest.main()

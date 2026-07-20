from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import Executor
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, PropertyMock, patch

from scripts.config.base import CJKCommonBuildOptions, ResolvedCJKBuildEntry
from scripts.pipeline import (
    FontmakeBuildContext,
    MapleBuildPipeline,
    PreparedFontmakeSource,
    build_cjk_extended_variable_outputs,
    build_woff2_fonts,
    collect_build_files,
    compile_fontmake_format,
    prepare_fontmake_sources,
    prune_build_files,
)
from scripts.config.resolver import BuildConfigResolver, BuildRuntimeContext
from scripts.cjk.models import CJKBuildConfig, CJKSourceConfig
from scripts.cjk.presets import CJKPresetId, build_preset_config, get_preset


def make_font_config():
    return BuildConfigResolver().load_defaults()


def make_runtime_context(tmp_path: Path) -> BuildRuntimeContext:
    return BuildRuntimeContext(
        src_dir="source",
        output_root=str(tmp_path / "fonts"),
        output_otf=str(tmp_path / "fonts" / "OTF"),
        output_ttf=str(tmp_path / "fonts" / "TTF"),
        output_ttf_hinted=str(tmp_path / "fonts" / "TTF-AutoHint"),
        output_variable=str(tmp_path / "fonts" / "Variable"),
        output_woff2=str(tmp_path / "fonts" / "Woff2"),
        output_nf=str(tmp_path / "fonts" / "NF"),
        ttf_base_dir=str(tmp_path / "fonts" / "TTF-AutoHint"),
        has_cache=False,
        is_nf_built=False,
        is_cjk_built=False,
        effective_github_mirror="github.com",
        font_forge_bin=None,
        resolved_vertical_metric=(1020, -300),
    )


def make_builtin_entry(locale: CJKPresetId = "cn") -> ResolvedCJKBuildEntry:
    preset_config = build_preset_config(locale)
    return ResolvedCJKBuildEntry(
        entry_id=locale,
        locale_name=preset_config.locale_name,
        build_config=preset_config,
        common_options=CJKCommonBuildOptions(),
        is_builtin=True,
        preset_id=locale,
        preset_spec=get_preset(locale),
    )


def make_custom_entry(locale_name: str = "HK") -> ResolvedCJKBuildEntry:
    return ResolvedCJKBuildEntry(
        entry_id=f"custom:{locale_name.lower()}",
        locale_name=locale_name,
        build_config=CJKBuildConfig(
            source=CJKSourceConfig(
                path=Path("source.ttf"),
                masters={100: {"wght": 100}, 400: {"wght": 400}, 800: {"wght": 800}},
            ),
            locale_name=locale_name,
        ),
        common_options=CJKCommonBuildOptions(),
        is_builtin=False,
    )


class MapleBuildPipelineDecisionTreeTest(unittest.TestCase):
    def test_prepare_sources_resolves_regular_vertical_metric(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            font_config = make_font_config()
            font_config.feature.line_height = 1.2
            runtime_context = make_runtime_context(tmp_path)
            executor_mock = MagicMock()
            executor_mock.map.return_value = (
                PreparedFontmakeSource(
                    "regular",
                    "regular.designspace",
                    (1100, -300),
                ),
                PreparedFontmakeSource(
                    "italic",
                    "italic.designspace",
                    (1080, -320),
                ),
            )

            context = prepare_fontmake_sources(
                font_config,
                runtime_context,
                cast(Executor, executor_mock),
            )

            self.assertEqual(runtime_context.resolved_vertical_metric, (1100, -300))
            self.assertEqual(len(context.sources), 2)

    def test_fontmake_format_filters_only_targeted_static_instances(self) -> None:
        context = FontmakeBuildContext(
            Path("temp"),
            Path("temp/variable"),
            Path("temp/ttf"),
            Path("temp/otf"),
            (
                PreparedFontmakeSource(
                    "regular",
                    "regular.designspace",
                    (1020, -300),
                ),
                PreparedFontmakeSource(
                    "italic",
                    "italic.designspace",
                    (1020, -300),
                ),
            ),
            (500, 600),
        )
        executor = cast(Executor, MagicMock())

        with patch("scripts.pipeline.compile_fontmake_branches") as compile_branches:
            compile_fontmake_format(
                context,
                "ttf",
                executor,
                target_styles=["Regular", "Bold", "Italic", "BoldItalic"],
            )
            static_jobs = compile_branches.call_args.args[0]

            compile_fontmake_format(context, "variable", executor)
            variable_jobs = compile_branches.call_args.args[0]

            compile_fontmake_format(context, "otf", executor)
            full_static_jobs = compile_branches.call_args.args[0]

        self.assertEqual(
            {job.interpolate for job in static_jobs},
            {r".* (?:Regular|Bold|Italic|BoldItalic)"},
        )
        self.assertEqual({job.interpolate for job in variable_jobs}, {False})
        self.assertEqual({job.interpolate for job in full_static_jobs}, {True})
        self.assertEqual(
            {job.width_transform for job in (*static_jobs, *variable_jobs)},
            {(500, 600)},
        )

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
                    "write_build_record",
                    side_effect=lambda: events.append("record"),
                ),
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
                    "scripts.pipeline.build_woff2_fonts",
                    side_effect=lambda *_: events.append("woff2"),
                ),
                patch(
                    "scripts.pipeline.prepare_fontmake_sources",
                    side_effect=lambda *_: events.append("prepare") or fontmake_context,
                ),
                patch(
                    "scripts.pipeline.build_variable_fonts",
                    side_effect=lambda *_: events.append("variable"),
                ),
                patch(
                    "scripts.pipeline.build_static_fonts",
                    side_effect=lambda *_args: events.append(_args[3]),
                ),
                patch(
                    "scripts.pipeline.build_base_fonts",
                    side_effect=lambda *_: events.append("ttf-autohint"),
                ),
                patch(
                    "scripts.pipeline.build_nerd_fonts",
                    side_effect=lambda *_: events.append("nf"),
                ),
                patch(
                    "scripts.pipeline.build_cjk_extended_static_outputs",
                    side_effect=lambda *_: events.append("cjk-static"),
                ),
                patch(
                    "scripts.pipeline.cleanup_unselected_base_formats",
                    side_effect=lambda *_: events.append("cleanup"),
                ),
            ):
                pipeline.build()

            self.assertEqual(
                events,
                [
                    "start",
                    "output-root",
                    "prepare",
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

    def test_build_reuses_cache_and_skips_optional_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.nerd_font.enable = False
            runtime_context = make_runtime_context(Path(tmp))
            runtime_context.has_cache = True
            events: list[str] = []

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            with patch.object(
                MapleBuildPipeline,
                "prepare_output_root",
                side_effect=lambda: events.append("prepare"),
            ):
                with patch.object(
                    MapleBuildPipeline,
                    "start_build_timer",
                    side_effect=lambda: events.append("start"),
                ):
                    with patch.object(
                        MapleBuildPipeline,
                        "reuse_base_output_cache",
                        side_effect=lambda: events.append("reuse"),
                    ):
                        with patch.object(
                            MapleBuildPipeline,
                            "write_build_record",
                            side_effect=lambda: events.append("record"),
                        ):
                            with patch.object(
                                MapleBuildPipeline,
                                "finish_build",
                                side_effect=lambda: events.append("finish"),
                            ):
                                with patch(
                                    "scripts.pipeline.prepare_fontmake_sources"
                                ) as prepare_sources_mock:
                                    with patch(
                                        "scripts.pipeline.build_variable_fonts"
                                    ) as build_variable_mock:
                                        with patch(
                                            "scripts.pipeline.build_static_fonts"
                                        ) as build_static_mock:
                                            with patch(
                                                "scripts.pipeline.build_base_fonts"
                                            ) as build_base_mock:
                                                with patch(
                                                    "scripts.pipeline.build_nerd_fonts"
                                                ) as build_nf_mock:
                                                    with patch(
                                                        "scripts.pipeline.build_cjk_extended_static_outputs"
                                                    ) as build_cjk_mock:
                                                        pipeline.build()

            self.assertEqual(events, ["start", "prepare", "reuse", "record", "finish"])
            prepare_sources_mock.assert_not_called()
            build_variable_mock.assert_not_called()
            build_static_mock.assert_not_called()
            build_base_mock.assert_not_called()
            build_nf_mock.assert_not_called()
            build_cjk_mock.assert_not_called()

    def test_woff2_stage_uses_static_ttf_outputs_and_skips_debug_builds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            font_config.behavior.formats = ["woff2"]
            pipeline = MapleBuildPipeline(font_config, runtime_context)

            output_ttf = Path(runtime_context.output_ttf)
            output_ttf.mkdir(parents=True)
            (output_ttf / "MapleMono-Regular.ttf").touch()

            executor = cast(Executor, MagicMock())
            with patch("scripts.pipeline.convert_to_web") as convert:
                build_woff2_fonts(font_config, runtime_context, executor)

            convert.assert_called_once_with(
                runtime_context.output_ttf,
                output_dir=runtime_context.output_woff2,
                flavor="woff2",
                executor=executor,
            )
            self.assertTrue(pipeline.should_build_woff2_outputs())

            font_config.behavior.debug = True
            self.assertFalse(pipeline.should_build_woff2_outputs())

    def test_reuse_base_output_cache_restores_vertical_metric(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            font_config = make_font_config()
            runtime_context = make_runtime_context(tmp_path)
            variable_dir = Path(runtime_context.output_variable)
            variable_dir.mkdir(parents=True, exist_ok=True)
            cached_font = variable_dir / f"{font_config.family_name_compact}[wght].ttf"
            cached_font.write_bytes(b"")

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            with patch(
                "scripts.pipeline.read_font_vertical_metric",
                return_value=(1200, -320),
            ) as read_metric_mock:
                pipeline.reuse_base_output_cache()

            self.assertEqual(runtime_context.resolved_vertical_metric, (1200, -320))
            read_metric_mock.assert_called_once_with(cached_font)

    def test_variable_cjk_outputs_use_entry_locale_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            font_config.cjk.entries = [make_custom_entry("HK")]
            captured_output_dirs: list[Path] = []

            with patch(
                "scripts.pipeline.build_cjk_extended_variable_fonts",
                side_effect=lambda entry, *_args: (
                    captured_output_dirs.append(_args[-2]) or None
                ),
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            self.assertEqual(
                captured_output_dirs,
                [Path(runtime_context.output_dir) / "Variable-HK"],
            )

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

                with patch("scripts.pipeline.logger.info") as log_info:
                    pipeline.start_build_timer()

                log_info.assert_called_once()
                message = log_info.call_args.args[0] % log_info.call_args.args[1:]
                self.assertTrue(
                    message.startswith("Build started: Maple Mono (Version")
                )
                self.assertIn("Formats: TTF, OTF, WOFF2 | Styles: all", message)
                self.assertIn("Hinting: enabled | Ligatures: enabled", message)
                self.assertIn("CJK: disabled | Cache: disabled", message)
                if width_summary is None:
                    self.assertNotIn("Width:", message)
                else:
                    self.assertIn(width_summary, message)

    def test_finish_logs_sorted_outputs_and_default_feature_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_context = make_runtime_context(tmp_path)
            output_root = Path(runtime_context.output_dir)
            for name in ["Variable", "TTF", "archive", ".cjk-temp", "temp"]:
                (output_root / name).mkdir(parents=True, exist_ok=True)
            (output_root / "build-config.json").write_text("{}", encoding="utf-8")
            font_config = make_font_config()
            pipeline = MapleBuildPipeline(font_config, runtime_context)
            pipeline.start_time = 10.0

            with (
                patch("scripts.pipeline.time.time", return_value=12.5),
                patch.object(
                    type(font_config),
                    "freeze_config_str",
                    new_callable=PropertyMock,
                    return_value="",
                ),
                patch("scripts.pipeline.logger.info") as log_info,
            ):
                pipeline.finish_build()

            message = log_info.call_args.args[0] % log_info.call_args.args[1:]
            self.assertIn("duration=2.50s", message)
            self.assertIn("fea=default config", message)
            self.assertIn("outputs=TTF,Variable,archive", message)
            self.assertNotIn(".cjk-temp", message)
            self.assertNotIn("build-config.json", message)
            self.assertIn(f"output_root={output_root.resolve()}", message)

    def test_cjk_warnings_explain_missing_selection_and_all_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()

            with patch("scripts.pipeline.logger.warning") as log_warning:
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            log_warning.assert_called_once_with(
                "Skip CJK outputs: reason=no CJK locale selected"
            )

            font_config.cjk.entries = [make_builtin_entry("cn")]
            with (
                patch(
                    "scripts.pipeline.build_cjk_extended_variable_fonts",
                    return_value=None,
                ),
                patch("scripts.pipeline.logger.warning") as log_warning,
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            self.assertTrue(
                any(
                    "locales=%s, mode=%s, reason=all selected locale builds failed"
                    in call.args[0]
                    for call in log_warning.call_args_list
                )
            )


class BuildFileSelectionTest(unittest.TestCase):
    def test_prune_and_collect_build_files_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for file_name in [
                "MapleMono-Regular.ttf",
                "MapleMono-Bold.ttf",
                "MapleMono-Light.ttf",
                "MapleMono-NF-Light.ttf",
            ]:
                (tmp_path / file_name).write_bytes(b"")

            prune_build_files(str(tmp_path), ["Regular", "Bold"], preserve_nf=True)
            collected = collect_build_files(str(tmp_path), ["Regular", "Bold"])

            self.assertEqual(collected, ["MapleMono-Bold.ttf", "MapleMono-Regular.ttf"])
            self.assertFalse((tmp_path / "MapleMono-Light.ttf").exists())
            self.assertTrue((tmp_path / "MapleMono-NF-Light.ttf").exists())


if __name__ == "__main__":
    unittest.main()

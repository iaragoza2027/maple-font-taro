from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import Executor
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from scripts.config.base import (
    BuildFormatId,
    CJKCommonBuildOptions,
    ResolvedCJKBuildEntry,
)
from scripts.pipeline.orchestrator import (
    FontmakeBuildContext,
    MapleBuildPipeline,
    PreparedFontmakeSource,
    build_base_fonts,
    build_woff2_fonts,
    compile_fontmake_formats,
    prepare_fontmake_sources,
)
from scripts.pipeline.cjk_outputs import (
    build_cjk_extended_variable_outputs,
    ensure_cjk_variable_fonts,
)
from scripts.pipeline.artifacts import collect_build_files, prune_build_files
from scripts.pipeline.cache import (
    CACHE_SCHEMA,
    output_snapshot,
    stage_digest,
    write_cache_record,
)
from scripts.config.resolver import BuildConfigResolver
from scripts.config.runtime import BuildRuntimeContext
from scripts.cjk.config import CJKBuildConfig, CJKOutputConfig, CJKSourceConfig
from scripts.cjk.presets import CJKPresetId, build_preset_config, get_preset
from scripts.cjk.variable import _cmap_supports_codepoint


TEST_STYLES = (
    "Thin",
    "ThinItalic",
    "ExtraLight",
    "ExtraLightItalic",
    "Light",
    "LightItalic",
    "Regular",
    "Italic",
    "Medium",
    "MediumItalic",
    "SemiBold",
    "SemiBoldItalic",
    "Bold",
    "BoldItalic",
    "ExtraBold",
    "ExtraBoldItalic",
)


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


def write_test_font(path: Path) -> None:
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef"])
    builder.setupCharacterMap({})
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph()})
    builder.setupHorizontalMetrics({".notdef": (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "familyName": "Maple Mono",
            "styleName": "Regular",
            "uniqueFontIdentifier": "Maple Mono Regular",
            "fullName": "Maple Mono Regular",
            "psName": "MapleMono-Regular",
        }
    )
    builder.setupOS2()
    builder.setupPost()
    builder.setupMaxp()
    path.parent.mkdir(parents=True, exist_ok=True)
    builder.save(path)


def make_stage_record(
    pipeline: MapleBuildPipeline,
    stage: str,
    paths: list[Path],
) -> dict[str, object]:
    return {
        "key": pipeline._stage_cache_identity(stage),
        "snapshot": output_snapshot(
            Path(pipeline.runtime_context.output_root),
            stage,
            paths,
        ),
    }


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
    def test_cjk_stage_logs_task_before_cache_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.cjk.entries = [make_custom_entry("JP")]
            runtime_context = make_runtime_context(Path(tmp))
            pipeline = MapleBuildPipeline(font_config, runtime_context)
            pipeline._cache_record = {"schema": CACHE_SCHEMA, "stages": {}}
            pipeline._cache_identity_checked = True
            pipeline._cache_identity_valid = True

            with (
                patch(
                    "scripts.pipeline.orchestrator.build_cjk_extended_static_outputs"
                ) as build_cjk,
                patch.object(pipeline, "_mark_stage_rebuilt"),
                patch("scripts.pipeline.orchestrator.logger.info") as log_info,
            ):
                pipeline._build_cjk_outputs(cast(Executor, MagicMock()))

            messages = [call.args[0] for call in log_info.call_args_list]
            self.assertEqual(
                messages[:2],
                [
                    "Build CJK static outputs (%s)",
                    "Cache miss: stage=%s, reason=missing-record",
                ],
            )
            build_cjk.assert_called_once()
            self.assertIsNotNone(build_cjk.call_args.kwargs["started_at"])

    def test_cjk_stage_invalidation_preserves_other_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fonts"
            root.mkdir()
            font_config = make_font_config()
            font_config.behavior.cache = True
            pipeline = MapleBuildPipeline(font_config, make_runtime_context(Path(tmp)))
            pipeline._cache_record = {
                "schema": CACHE_SCHEMA,
                "stages": {
                    "jp-static": {"key": "old-jp"},
                    "cn-static": {"key": "keep-cn"},
                },
            }
            pipeline._invalidate_recorded_stage("jp-static")

            record = json.loads((root / "build-cache.json").read_text())
            self.assertEqual(record["stages"], {"cn-static": {"key": "keep-cn"}})

    def test_cjk_stage_paths_only_include_target_styles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.debug = True
            font_config.cjk.entries = [make_custom_entry("JP")]
            runtime_context = make_runtime_context(Path(tmp))
            output_dir = Path(runtime_context.output_root) / "JP"
            write_test_font(output_dir / "MapleMono-JP-Regular.ttf")
            write_test_font(output_dir / "MapleMono-JP-Italic.ttf")
            write_test_font(output_dir / "MapleMono-JP-Bold.ttf")

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            self.assertEqual(
                {path.name for path in pipeline._cjk_stage_paths("JP")},
                {"MapleMono-JP-Regular.ttf", "MapleMono-JP-Italic.ttf"},
            )

    def test_nf_stage_uses_generic_cache_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.cjk.entries = [make_custom_entry("JP")]
            runtime_context = make_runtime_context(Path(tmp))
            pipeline = MapleBuildPipeline(font_config, runtime_context)
            nf_paths = pipeline._nf_stage_expected_paths()
            for nf_path in nf_paths:
                write_test_font(nf_path)
            pipeline._cache_record = {
                "schema": CACHE_SCHEMA,
                "stages": {
                    "nf": {
                        "key": "nf-key",
                        "snapshot": output_snapshot(
                            Path(runtime_context.output_root),
                            "nf",
                            nf_paths,
                        ),
                    }
                },
            }
            pipeline._cache_identity_checked = True
            pipeline._cache_identity_valid = True

            with patch.object(pipeline, "_stage_cache_identity", return_value="nf-key"):
                self.assertTrue(pipeline._validate_recorded_stage("nf"))

    def test_cjk_variable_stage_paths_only_include_current_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cjk_output_format = "variable"
            font_config.cjk.entries = [make_custom_entry("JP")]
            runtime_context = make_runtime_context(Path(tmp))
            output_dir = Path(runtime_context.output_root) / "Variable-JP"
            write_test_font(output_dir / "MapleMono-JP[wght].ttf")
            write_test_font(output_dir / "MapleMono-JP-Italic[wght].ttf")
            write_test_font(output_dir / "MapleMono-OLD[wght].ttf")

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            self.assertEqual(
                {path.name for path in pipeline._cjk_stage_paths("JP")},
                {"MapleMono-JP[wght].ttf", "MapleMono-JP-Italic[wght].ttf"},
            )

    def test_cjk_variable_source_uses_effective_github_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entry = make_custom_entry()
            entry.build_config = CJKBuildConfig(
                source=entry.build_config.source,
                output=CJKOutputConfig(dir=Path(tmp)),
            )

            font_config = make_font_config()

            def build_outputs(*_args, **_kwargs) -> None:
                write_test_font(Path(tmp) / "MapleMono-CJK-VF.ttf")
                write_test_font(Path(tmp) / "MapleMono-CJK-Italic-VF.ttf")

            with (
                patch(
                    "scripts.pipeline.cjk_outputs.build_cjk_fonts",
                    side_effect=build_outputs,
                ) as build,
                patch("scripts.pipeline.cjk_outputs.logger.info") as log_info,
            ):
                result = ensure_cjk_variable_fonts(
                    entry,
                    font_config,
                    "mirror.example.com/github.com",
                )

            self.assertEqual(
                result,
                (
                    Path(tmp) / "MapleMono-CJK-VF.ttf",
                    Path(tmp) / "MapleMono-CJK-Italic-VF.ttf",
                ),
            )
            build.assert_called_once_with(
                entry.build_config,
                font_config,
                vf_only=True,
                executor=None,
                github_mirror="mirror.example.com/github.com",
            )
            log_info.assert_called_once_with("Build CJK variable fonts: %s", "HK")

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
            jobs = executor_mock.map.call_args.args[1]
            self.assertEqual(
                {job.feature_file_path for job in jobs},
                {
                    "source/features/regular.fea",
                    "source/features/italic.fea",
                },
            )
            self.assertTrue(all(job.font_config is font_config for job in jobs))

    def test_fontmake_formats_compile_all_branches_in_one_batch(self) -> None:
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

        with patch(
            "scripts.pipeline.orchestrator.compile_fontmake_branches"
        ) as compile_branches:
            compile_fontmake_formats(
                context,
                ("variable", "ttf", "otf"),
                executor,
                target_styles=["Regular", "Bold", "Italic", "BoldItalic"],
            )
            jobs = compile_branches.call_args.args[0]

        compile_branches.assert_called_once()
        self.assertEqual(len(jobs), 6)
        variable_jobs = [job for job in jobs if job.output == "variable"]
        static_jobs = [job for job in jobs if job.output != "variable"]
        self.assertEqual(
            {job.interpolate for job in static_jobs},
            {r".* (?:Regular|Bold|Italic|BoldItalic)"},
        )
        self.assertEqual({job.interpolate for job in variable_jobs}, {False})
        self.assertEqual({job.output for job in jobs}, {"variable", "ttf", "otf"})
        self.assertEqual(
            {job.width_transform for job in jobs},
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

    def test_hinted_ttf_demand_matrix(self) -> None:
        font_config = make_font_config()
        font_config.nerd_font.enable = False
        font_config.cjk.entries = []

        cases = (
            ((["ttf"], True, "static", []), True),
            ((["otf"], True, "static", []), False),
            ((["woff2"], True, "static", []), False),
            ((["otf"], False, "static", [make_builtin_entry("cn")]), False),
            ((["otf"], True, "variable", [make_builtin_entry("cn")]), False),
            ((["otf"], True, "static", [make_builtin_entry("cn")]), True),
        )
        for (formats, hinted, cjk_format, entries), expected in cases:
            with self.subTest(
                formats=formats,
                hinted=hinted,
                cjk_format=cjk_format,
                cjk=bool(entries),
            ):
                font_config.behavior.formats = cast(list[BuildFormatId], formats)
                font_config.feature.hinted = hinted
                font_config.behavior.cjk_output_format = cjk_format
                font_config.cjk.entries = entries
                self.assertEqual(font_config.needs_hinted_ttf(), expected)

        font_config.behavior.formats = ["otf"]
        font_config.feature.hinted = True
        font_config.behavior.cjk_output_format = "static"
        font_config.nerd_font.enable = True
        font_config.cjk.entries = [make_builtin_entry("cn")]
        self.assertTrue(font_config.needs_hinted_ttf())

        font_config.behavior.use_cjk_both = True
        self.assertTrue(font_config.needs_hinted_ttf())

    def test_cache_record_omits_cleaned_intermediate_ttf_stages(self) -> None:
        font_config = make_font_config()
        font_config.behavior.formats = ["otf"]
        font_config.feature.hinted = True
        font_config.nerd_font.enable = True
        pipeline = MapleBuildPipeline(
            font_config,
            make_runtime_context(Path("/tmp/maple-font-cache-stage-test")),
        )

        self.assertTrue(font_config.needs_hinted_ttf())
        self.assertNotIn("ttf", pipeline._requested_cache_stages())
        self.assertNotIn("ttf-autohint", pipeline._requested_cache_stages())

    def test_otf_only_build_skips_unconsumed_autohint_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.formats = ["otf"]
            font_config.nerd_font.enable = False
            font_config.cjk.entries = []
            runtime_context = make_runtime_context(Path(tmp))
            temp_path = Path(tmp) / "fonts" / "temp"
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
                patch.object(MapleBuildPipeline, "write_build_record"),
                patch.object(MapleBuildPipeline, "_mark_stage_rebuilt"),
                patch.object(MapleBuildPipeline, "finish_build"),
                patch(
                    "scripts.pipeline.orchestrator.prepare_fontmake_sources",
                    return_value=context,
                ),
                patch("scripts.pipeline.orchestrator.compile_fontmake_formats"),
                patch("scripts.pipeline.orchestrator.build_variable_fonts"),
                patch("scripts.pipeline.orchestrator.build_static_fonts"),
                patch("scripts.pipeline.orchestrator.build_base_fonts") as autohint,
                patch("scripts.pipeline.orchestrator.cleanup_unselected_base_formats"),
            ):
                pipeline.build()

            autohint.assert_not_called()

    def test_build_reuses_cache_and_skips_optional_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.nerd_font.enable = False
            runtime_context = make_runtime_context(Path(tmp))
            runtime_context.has_cache = True
            variable_dir = Path(runtime_context.output_variable)
            variable_dir.mkdir(parents=True, exist_ok=True)
            write_test_font(variable_dir / "MapleMono[wght].ttf")
            write_test_font(variable_dir / "MapleMono-Italic[wght].ttf")
            for directory, suffix in (
                (Path(runtime_context.output_ttf), ".ttf"),
                (Path(runtime_context.output_ttf_hinted), ".ttf"),
                (Path(runtime_context.output_otf), ".otf"),
                (Path(runtime_context.output_woff2), ".woff2"),
            ):
                directory.mkdir(parents=True, exist_ok=True)
                for style in TEST_STYLES:
                    file_name = (
                        f"MapleMono-{style}.ttf.woff2"
                        if suffix == ".woff2"
                        else f"MapleMono-{style}{suffix}"
                    )
                    write_test_font(directory / file_name)
            events: list[str] = []

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            for stage in ("variable", "ttf", "otf", "ttf-autohint", "woff2"):
                pipeline._mark_stage_rebuilt(
                    stage,
                    pipeline._base_stage_expected_paths(stage),
                )
            pipeline.write_build_record()
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
                                    "scripts.pipeline.orchestrator.prepare_fontmake_sources"
                                ) as prepare_sources_mock:
                                    with patch(
                                        "scripts.pipeline.orchestrator.build_variable_fonts"
                                    ) as build_variable_mock:
                                        with patch(
                                            "scripts.pipeline.orchestrator.build_static_fonts"
                                        ) as build_static_mock:
                                            with patch(
                                                "scripts.pipeline.orchestrator.build_base_fonts"
                                            ) as build_base_mock:
                                                with patch(
                                                    "scripts.pipeline.orchestrator.build_nerd_fonts"
                                                ) as build_nf_mock:
                                                    with patch(
                                                        "scripts.pipeline.orchestrator.build_cjk_extended_static_outputs"
                                                    ) as build_cjk_mock:
                                                        pipeline.build()

            self.assertEqual(events, ["start", "prepare", "reuse", "record", "finish"])
            prepare_sources_mock.assert_not_called()
            build_variable_mock.assert_not_called()
            build_static_mock.assert_not_called()
            build_base_mock.assert_not_called()
            build_nf_mock.assert_not_called()
            build_cjk_mock.assert_not_called()

    def test_all_cache_hits_are_hashed_only_during_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.behavior.formats = ["otf"]
            font_config.feature.hinted = False
            font_config.behavior.least_styles = True
            font_config.nerd_font.enable = False
            font_config.cjk.entries = []
            runtime_context = make_runtime_context(Path(tmp))

            seeded = MapleBuildPipeline(font_config, runtime_context)
            for stage in ("variable", "otf"):
                paths = seeded._base_stage_expected_paths(stage)
                for path in paths:
                    write_test_font(path)
                seeded._mark_stage_rebuilt(stage, paths)
            seeded.write_cache_record()
            original_record = json.loads(
                (Path(runtime_context.output_root) / "build-cache.json").read_text()
            )

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            with patch(
                "scripts.pipeline.cache.stage_digest",
                wraps=stage_digest,
            ) as digest:
                self.assertEqual(pipeline.base_formats_to_build(), ())
                pipeline.write_cache_record()

            self.assertEqual(digest.call_count, 2)
            self.assertEqual(
                json.loads(
                    (Path(runtime_context.output_root) / "build-cache.json").read_text()
                ),
                original_record,
            )

    def test_mixed_cache_reuses_hits_and_snapshots_only_rebuilt_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.behavior.formats = ["otf"]
            font_config.feature.hinted = False
            font_config.behavior.least_styles = True
            font_config.nerd_font.enable = False
            font_config.cjk.entries = []
            runtime_context = make_runtime_context(Path(tmp))
            root = Path(runtime_context.output_root)

            seeded = MapleBuildPipeline(font_config, runtime_context)
            paths_by_stage = {
                stage: seeded._base_stage_expected_paths(stage)
                for stage in ("variable", "otf")
            }
            for paths in paths_by_stage.values():
                for path in paths:
                    write_test_font(path)
            original_variable = make_stage_record(
                seeded,
                "variable",
                paths_by_stage["variable"],
            )
            record = {
                "schema": CACHE_SCHEMA,
                "stages": {
                    "variable": original_variable,
                    "otf": make_stage_record(
                        seeded,
                        "otf",
                        paths_by_stage["otf"],
                    ),
                    "ttf": {
                        "key": "stale",
                        "snapshot": {
                            "files": ["TTF/Stale.ttf"],
                            "digest": "stale",
                        },
                    },
                },
            }
            write_cache_record(root, record)
            paths_by_stage["otf"][0].write_bytes(b"corrupt")

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            with patch(
                "scripts.pipeline.cache.stage_digest",
                wraps=stage_digest,
            ) as digest:
                self.assertEqual(pipeline.base_formats_to_build(), ("otf",))
                for path in paths_by_stage["otf"]:
                    write_test_font(path)
                pipeline._mark_stage_rebuilt("otf", paths_by_stage["otf"])
                pipeline.write_cache_record()

            current_record = json.loads((root / "build-cache.json").read_text())
            self.assertEqual(digest.call_count, 3)
            self.assertEqual(
                current_record["stages"]["variable"],
                original_variable,
            )
            self.assertEqual(set(current_record["stages"]), {"variable", "otf"})

    def test_failed_rebuild_does_not_restore_invalidated_stage_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.behavior.formats = ["otf"]
            font_config.feature.hinted = False
            font_config.behavior.least_styles = True
            font_config.nerd_font.enable = False
            font_config.cjk.entries = []
            runtime_context = make_runtime_context(Path(tmp))
            root = Path(runtime_context.output_root)
            seeded = MapleBuildPipeline(font_config, runtime_context)

            variable_paths = seeded._base_stage_expected_paths("variable")
            otf_paths = seeded._base_stage_expected_paths("otf")
            for path in (*variable_paths, *otf_paths):
                write_test_font(path)
            otf_record = make_stage_record(seeded, "otf", otf_paths)
            otf_record["key"] = "obsolete"
            write_cache_record(
                root,
                {
                    "schema": CACHE_SCHEMA,
                    "stages": {
                        "variable": make_stage_record(
                            seeded,
                            "variable",
                            variable_paths,
                        ),
                        "otf": otf_record,
                    },
                },
            )

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            with (
                patch(
                    "scripts.pipeline.orchestrator.prepare_fontmake_sources",
                    side_effect=RuntimeError("build failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "build failed"),
            ):
                pipeline.build()

            record = json.loads((root / "build-cache.json").read_text())
            self.assertEqual(set(record["stages"]), {"variable"})

    def test_cjk_profiles_reuse_and_rebuild_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.behavior.debug = True
            font_config.behavior.use_cjk_both = True
            font_config.cjk.entries = [make_custom_entry("HK")]
            runtime_context = make_runtime_context(Path(tmp))
            runtime_context.is_nf_built = True
            root = Path(runtime_context.output_root)
            seeded = MapleBuildPipeline(font_config, runtime_context)
            hk_paths = seeded._cjk_stage_expected_paths("HK")
            nf_hk_paths = seeded._cjk_stage_expected_paths("NF-HK")
            for path in (*hk_paths, *nf_hk_paths):
                write_test_font(path)
            hk_record = make_stage_record(seeded, "hk-static", hk_paths)
            write_cache_record(
                root,
                {
                    "schema": CACHE_SCHEMA,
                    "stages": {
                        "hk-static": hk_record,
                        "nf-hk-static": make_stage_record(
                            seeded,
                            "nf-hk-static",
                            nf_hk_paths,
                        ),
                    },
                },
            )
            nf_hk_paths[0].write_bytes(b"corrupt")

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            with patch(
                "scripts.pipeline.cache.stage_digest",
                wraps=stage_digest,
            ) as digest:
                self.assertTrue(pipeline._validate_recorded_stage("hk-static"))
                self.assertFalse(pipeline._validate_recorded_stage("nf-hk-static"))
                pipeline._invalidate_recorded_stage("nf-hk-static")
                write_test_font(nf_hk_paths[0])
                pipeline._mark_stage_rebuilt("nf-hk-static", nf_hk_paths)
                pipeline.write_cache_record()

            current_record = json.loads((root / "build-cache.json").read_text())
            self.assertEqual(digest.call_count, 3)
            self.assertEqual(current_record["stages"]["hk-static"], hk_record)
            self.assertEqual(
                set(current_record["stages"]),
                {"hk-static", "nf-hk-static"},
            )

    def test_cache_builds_only_missing_base_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.nerd_font.enable = False
            runtime_context = make_runtime_context(Path(tmp))

            for directory, suffix in (
                (Path(runtime_context.output_variable), "[wght].ttf"),
                (Path(runtime_context.output_ttf), ".ttf"),
                (Path(runtime_context.output_ttf_hinted), ".ttf"),
                (Path(runtime_context.output_woff2), ".woff2"),
            ):
                directory.mkdir(parents=True, exist_ok=True)
                if suffix == "[wght].ttf":
                    write_test_font(directory / "MapleMono[wght].ttf")
                    write_test_font(directory / "MapleMono-Italic[wght].ttf")
                else:
                    for style in TEST_STYLES:
                        file_name = (
                            f"MapleMono-{style}.ttf.woff2"
                            if suffix == ".woff2"
                            else f"MapleMono-{style}{suffix}"
                        )
                        write_test_font(directory / file_name)

            write_test_font(
                Path(runtime_context.output_variable) / "MapleMonoDebug[wght].ttf"
            )
            for directory, suffix in (
                (Path(runtime_context.output_ttf), ".ttf"),
                (Path(runtime_context.output_ttf_hinted), ".ttf"),
                (Path(runtime_context.output_woff2), ".ttf.woff2"),
            ):
                write_test_font(directory / f"MapleMonoDebug-Regular{suffix}")

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            for stage in ("variable", "ttf", "ttf-autohint", "woff2"):
                pipeline._mark_stage_rebuilt(
                    stage,
                    pipeline._base_stage_expected_paths(stage),
                )
            pipeline.write_build_record()
            record = json.loads(
                (Path(runtime_context.output_root) / "build-cache.json").read_text(
                    encoding="utf-8"
                )
            )
            recorded_files = {
                path
                for stage in record["stages"].values()
                for path in stage["snapshot"]["files"]
            }
            self.assertFalse(any("Debug" in path for path in recorded_files))
            self.assertEqual(pipeline.base_formats_to_build(), ("otf",))

            Path(runtime_context.output_otf).mkdir(parents=True, exist_ok=True)
            for style in TEST_STYLES:
                write_test_font(
                    Path(runtime_context.output_otf) / f"MapleMono-{style}.otf"
                )
            write_test_font(
                Path(runtime_context.output_otf) / "MapleMonoDebug-Regular.otf"
            )
            pipeline._mark_stage_rebuilt(
                "otf",
                pipeline._base_stage_expected_paths("otf"),
            )
            pipeline.write_build_record()
            self.assertEqual(pipeline.base_formats_to_build(), ())

            logging_pipeline = MapleBuildPipeline(font_config, runtime_context)
            with patch("scripts.pipeline.orchestrator.logger.info") as log_info:
                logging_pipeline.base_formats_to_build()
                logging_pipeline.should_build_hinted_ttf(("otf",))
                logging_pipeline.should_build_woff2_outputs(("otf",))

            messages = [call.args[0] for call in log_info.call_args_list]
            self.assertIn("Reuse cached %s outputs", messages)
            self.assertIn("Reuse cached TTF-AutoHint outputs", messages)
            self.assertIn("Reuse cached WOFF2 outputs", messages)

    def test_cache_identity_miss_does_not_delete_unrelated_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            font_config = make_font_config()
            font_config.behavior.cache = True
            runtime_context = make_runtime_context(tmp_path)
            output_root = Path(runtime_context.output_root)
            output_root.mkdir(parents=True, exist_ok=True)
            (output_root / "build-config.json").write_text(
                '{"family_name": "Other Font"}',
                encoding="utf-8",
            )
            stale_output = output_root / "stale-output.ttf"
            stale_output.touch()

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            with (
                patch("scripts.pipeline.orchestrator.logger.debug") as log_debug,
            ):
                self.assertEqual(
                    pipeline.base_formats_to_build(),
                    ("variable", "ttf", "otf"),
                )
                pipeline.prepare_output_root()

            self.assertTrue(stale_output.exists())
            self.assertNotIn(
                "Clean invalidated build cache",
                [call.args[0] for call in log_debug.call_args_list],
            )

    def test_cache_identity_tracks_dimensions_but_not_runtime_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "source"
            source_dir.mkdir()
            designspace_text = (
                "<designspace format='5.0'><lib><dict>"
                "<key>GSDimensionPlugin.Dimensions</key><dict>"
                "<key>dimension-a</key><dict/></dict>"
                "</dict></lib></designspace>"
            )
            designspace = source_dir / "MapleMono[wght].designspace"
            italic_designspace = source_dir / "MapleMono-Italic[wght].designspace"
            designspace.write_text(designspace_text, encoding="utf-8")
            italic_designspace.write_text(designspace_text, encoding="utf-8")

            font_config = make_font_config()
            font_config.behavior.cache = True
            runtime_context = make_runtime_context(tmp_path)
            runtime_context.src_dir = str(source_dir)
            Path(runtime_context.output_root).mkdir(parents=True)
            pipeline = MapleBuildPipeline(font_config, runtime_context)
            pipeline.write_build_record()
            build_config = json.loads(
                (Path(runtime_context.output_root) / "build-config.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertNotIn("cache_identity", build_config)

            font_config.behavior.archive = not font_config.behavior.archive
            font_config.metrics.pool_size += 1
            unchanged = MapleBuildPipeline(font_config, runtime_context)
            self.assertTrue(unchanged._cache_matches_build())
            unchanged_key = unchanged._stage_cache_identity("ttf")

            designspace.write_text(
                designspace_text.replace("dimension-a", "dimension-b"),
                encoding="utf-8",
            )
            changed = MapleBuildPipeline(font_config, runtime_context)
            self.assertNotEqual(
                changed._stage_cache_identity("ttf"),
                unchanged_key,
            )

    def test_cache_record_excludes_archive_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            font_config = make_font_config()
            runtime_context = make_runtime_context(tmp_path)
            variable_dir = Path(runtime_context.output_variable)
            write_test_font(variable_dir / "MapleMono[wght].ttf")
            write_test_font(variable_dir / "MapleMono-Italic[wght].ttf")
            archive_dir = Path(runtime_context.output_root) / "archive"
            archive_dir.mkdir(parents=True)
            (archive_dir / "release.zip").write_bytes(b"archive")

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            pipeline._mark_stage_rebuilt(
                "variable",
                pipeline._base_stage_expected_paths("variable"),
            )
            pipeline.write_build_record()

            record = json.loads(
                (Path(runtime_context.output_root) / "build-cache.json").read_text(
                    encoding="utf-8"
                )
            )
            recorded_paths = {
                path
                for stage in record["stages"].values()
                for path in stage["snapshot"]["files"]
            }
            self.assertFalse(
                any(path.startswith("archive/") for path in recorded_paths)
            )

    def test_fonts_cache_record_excludes_source_cjk_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_context = make_runtime_context(tmp_path)
            font_config = make_font_config()
            font_config.behavior.cache = True
            entry = make_custom_entry("JP")
            source_cache_dir = tmp_path / "source" / "cjk" / "jp"
            entry.build_config = CJKBuildConfig(
                source=entry.build_config.source,
                output=CJKOutputConfig(dir=source_cache_dir),
            )
            font_config.cjk.entries = [entry]

            source_marker = source_cache_dir / "MapleMono-JP-VF.ttf"
            source_marker.parent.mkdir(parents=True)
            source_marker.write_bytes(b"source-cache")
            font_config.behavior.debug = True
            pipeline = MapleBuildPipeline(font_config, runtime_context)
            for final_output in pipeline._cjk_stage_expected_paths("JP"):
                write_test_font(final_output)
            pipeline._mark_stage_rebuilt(
                "jp-static",
                pipeline._cjk_stage_expected_paths("JP"),
            )
            pipeline.write_build_record()

            record = json.loads(
                (Path(runtime_context.output_root) / "build-cache.json").read_text(
                    encoding="utf-8"
                )
            )
            recorded_paths = {
                path
                for stage in record["stages"].values()
                for path in stage["snapshot"]["files"]
            }
            self.assertEqual(
                recorded_paths,
                {
                    "JP/MapleMono-JP-Regular.ttf",
                    "JP/MapleMono-JP-Italic.ttf",
                },
            )
            self.assertTrue(source_marker.is_file())

    def test_cjk_cache_stages_split_locale_and_nf_profiles(self) -> None:
        runtime_context = make_runtime_context(Path("/tmp/maple-font-stage-test"))
        font_config = make_font_config()
        font_config.behavior.use_cjk_both = True
        font_config.cjk.entries = [make_custom_entry("HK"), make_custom_entry("JP")]
        runtime_context.is_nf_built = True
        pipeline = MapleBuildPipeline(font_config, runtime_context)

        self.assertEqual(
            [stage for stage, _entry, _locale in pipeline._cjk_stage_targets()],
            [
                "nf-hk-static",
                "hk-static",
                "nf-jp-static",
                "jp-static",
            ],
        )
        self.assertNotEqual(
            pipeline._stage_cache_identity("hk-static"),
            pipeline._stage_cache_identity("jp-static"),
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

            executor = cast(Executor, MagicMock())
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

            executor = cast(Executor, MagicMock())
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
                "scripts.pipeline.orchestrator.read_font_vertical_metric",
                return_value=(1200, -320),
            ) as read_metric_mock:
                pipeline.reuse_base_output_cache()

            self.assertEqual(runtime_context.resolved_vertical_metric, (1200, -320))
            read_metric_mock.assert_called_once_with(cached_font)

    def test_variable_cjk_outputs_use_nf_entry_locale_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            font_config.cjk.entries = [make_custom_entry("HK")]
            captured_output_dirs: list[Path] = []

            with patch(
                "scripts.pipeline.cjk_outputs.build_cjk_extended_variable_fonts",
                side_effect=lambda entry, *_args, **kwargs: (
                    captured_output_dirs.append(kwargs["output_locale"])
                    or (Path("regular"), Path("italic"))
                ),
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            self.assertEqual(captured_output_dirs, ["NF-HK"])

    def test_variable_cjk_outputs_build_both_nf_profiles_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            font_config.behavior.use_cjk_both = True
            font_config.cjk.entries = [make_custom_entry("HK")]
            captured_profiles: list[tuple[str, bool]] = []

            with patch(
                "scripts.pipeline.cjk_outputs.build_cjk_extended_variable_fonts",
                side_effect=lambda entry, *_args, **kwargs: (
                    captured_profiles.append(
                        (kwargs["output_locale"], kwargs["include_nerd_font"])
                    )
                    or (Path("regular"), Path("italic"))
                ),
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            self.assertEqual(captured_profiles, [("NF-HK", True), ("HK", False)])

    def test_variable_cmap_limits_codepoints_by_subtable_format(self) -> None:
        self.assertTrue(_cmap_supports_codepoint(4, 0xFFFF))
        self.assertFalse(_cmap_supports_codepoint(4, 0x10000))
        self.assertTrue(_cmap_supports_codepoint(12, 0x10000))

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

    def test_missing_cjk_selection_logs_reason_outside_ci(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()

            with (
                patch("scripts.pipeline.cjk_outputs.is_ci", return_value=False),
                patch("scripts.pipeline.cjk_outputs.logger.warning") as log_warning,
                patch("scripts.pipeline.cjk_outputs.logger.debug") as log_debug,
                patch("scripts.pipeline.cjk_outputs.logger.info") as log_info,
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            log_warning.assert_not_called()
            log_debug.assert_not_called()
            log_info.assert_called_once_with(
                "Skip CJK outputs: reason=no CJK locale selected"
            )

    def test_missing_cjk_selection_stays_quiet_in_ci(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()

            with (
                patch("scripts.pipeline.cjk_outputs.is_ci", return_value=True),
                patch("scripts.pipeline.cjk_outputs.logger.debug") as log_debug,
                patch("scripts.pipeline.cjk_outputs.logger.info") as log_info,
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            log_info.assert_not_called()
            log_debug.assert_called_once_with(
                "Skip CJK outputs because no locale is selected"
            )

    def test_cjk_internal_missing_file_propagates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            font_config.cjk.entries = [make_builtin_entry("cn")]

            with (
                patch(
                    "scripts.pipeline.cjk_outputs.build_cjk_extended_variable_fonts",
                    side_effect=FileNotFoundError("missing intermediate"),
                ),
                self.assertRaisesRegex(FileNotFoundError, "missing intermediate"),
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)


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

    def test_autohint_missing_input_fails_before_parallel_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            missing = Path(runtime_context.output_ttf) / "MapleMono-Regular.ttf"
            executor = cast(Executor, MagicMock())

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
            executor = cast(Executor, MagicMock())

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


if __name__ == "__main__":
    unittest.main()

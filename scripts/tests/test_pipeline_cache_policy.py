from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, call, patch

from scripts.cjk.config import CJKBuildConfig, CJKOutputConfig
from scripts.pipeline.cache import (
    CACHE_SCHEMA,
    stage_digest,
    write_cache_record,
)
from scripts.pipeline.fontmake import (
    FontmakeBuildContext,
)
from scripts.pipeline.orchestrator import MapleBuildPipeline
from scripts.tests.pipeline_fixtures import (
    TEST_STYLES,
    make_builtin_entry,
    make_custom_entry,
    make_font_config,
    make_runtime_context,
    make_stage_record,
    write_test_font,
)
from scripts.utils.logging import TaskName

if TYPE_CHECKING:
    from scripts.config.base import (
        BuildFormatId,
    )


class PipelineCachePolicyTest(unittest.TestCase):
    def test_stage_cache_validation_header_precedes_each_non_cjk_miss(self) -> None:
        font_config = make_font_config()
        font_config.behavior.cache = True
        pipeline = MapleBuildPipeline(
            font_config,
            make_runtime_context(Path("maple-font-cache-log-test")),
        )
        pipeline._cache_record = {"schema": CACHE_SCHEMA, "stages": {}}
        pipeline._cache_identity_checked = True
        pipeline._cache_identity_valid = True
        task_names = {
            "variable": TaskName.VARIABLE,
            "ttf": TaskName.TTF,
            "otf": TaskName.OTF,
            "ttf-autohint": TaskName.TTF_AUTOHINT,
            "woff2": TaskName.WOFF2,
            "nf": TaskName.NERD_FONT,
            "nf-variable": TaskName.NERD_FONT,
        }

        manager = MagicMock()
        manager.log_task.return_value = 1.0
        with (
            patch("scripts.pipeline.orchestrator.log_task", manager.log_task),
            patch("scripts.pipeline.orchestrator.logger.info", manager.info),
            patch.object(pipeline, "_stage_cache_identity", return_value="key"),
        ):
            for stage, task_name in task_names.items():
                with self.subTest(stage=stage):
                    manager.reset_mock()

                    self.assertFalse(pipeline._validate_cached_stage(stage, []))

                    self.assertEqual(
                        manager.mock_calls,
                        [
                            call.log_task(
                                task_name,
                                "Validate stage cache: stage=%s",
                                stage,
                                force_separator=True,
                            ),
                            call.info(
                                "Cache miss: stage=%s, reason=missing-record",
                                stage,
                            ),
                        ],
                    )

    def test_missing_cache_record_is_reported_after_each_stage_header(self) -> None:
        font_config = make_font_config()
        font_config.behavior.cache = True
        pipeline = MapleBuildPipeline(
            font_config,
            make_runtime_context(Path("maple-font-missing-cache-log-test")),
        )
        manager = MagicMock()
        manager.log_task.return_value = 1.0

        with (
            patch("scripts.pipeline.orchestrator.log_task", manager.log_task),
            patch("scripts.pipeline.orchestrator.logger.info", manager.info),
            patch("scripts.pipeline.orchestrator.read_cache_record", return_value=None),
        ):
            self.assertFalse(pipeline._validate_cached_stage("variable", []))

        self.assertEqual(
            manager.mock_calls,
            [
                call.log_task(
                    TaskName.VARIABLE,
                    "Validate stage cache: stage=%s",
                    "variable",
                    force_separator=True,
                ),
                call.info(
                    "Cache miss: stage=%s, reason=missing-cache-record path=%s",
                    "variable",
                    "build-cache.json",
                ),
            ],
        )
        self.assertNotIn(
            "Cache miss: stage=all, reason=missing-cache-record path=%s",
            [mock_call.args[0] for mock_call in manager.info.call_args_list],
        )

    def test_cache_hit_precedes_reuse_log_in_the_stage_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            runtime_context = make_runtime_context(Path(tmp))
            seeded = MapleBuildPipeline(font_config, runtime_context)
            paths = seeded._base_stage_expected_paths("variable")
            for path in paths:
                write_test_font(path)

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            pipeline._cache_record = {
                "schema": CACHE_SCHEMA,
                "stages": {
                    "variable": make_stage_record(seeded, "variable", paths),
                },
            }
            pipeline._cache_identity_checked = True
            pipeline._cache_identity_valid = True
            manager = MagicMock()
            manager.log_task.return_value = 1.0

            with (
                patch("scripts.pipeline.orchestrator.log_task", manager.log_task),
                patch("scripts.pipeline.orchestrator.logger.info", manager.info),
            ):
                self.assertTrue(pipeline._has_cached_base_format("variable"))
                pipeline._log_cache_reuse("variable")

            self.assertEqual(
                manager.mock_calls,
                [
                    call.log_task(
                        TaskName.VARIABLE,
                        "Validate stage cache: stage=%s",
                        "variable",
                        force_separator=True,
                    ),
                    call.info("Cache hit: stage=%s", "variable"),
                    call.info("Reuse cached %s outputs", "VARIABLE"),
                ],
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
                font_config.behavior.formats = cast("list[BuildFormatId]", formats)
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
                        f"MapleMono-{style}.woff2"
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
            with patch.object(  # noqa: SIM117
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
                            f"MapleMono-{style}.woff2"
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
                (Path(runtime_context.output_woff2), ".woff2"),
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

    def test_base_cache_identity_ignores_hinting_but_downstream_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            hinted = make_font_config()
            hinted.feature.hinted = True
            unhinted = make_font_config()
            unhinted.feature.hinted = False

            hinted_pipeline = MapleBuildPipeline(hinted, runtime_context)
            unhinted_pipeline = MapleBuildPipeline(unhinted, runtime_context)

            self.assertEqual(
                hinted_pipeline._stage_cache_identity("variable"),
                unhinted_pipeline._stage_cache_identity("variable"),
            )
            self.assertEqual(
                hinted_pipeline._stage_cache_identity("ttf"),
                unhinted_pipeline._stage_cache_identity("ttf"),
            )
            self.assertNotEqual(
                hinted_pipeline._stage_cache_identity("ttf-autohint"),
                unhinted_pipeline._stage_cache_identity("ttf-autohint"),
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


if __name__ == "__main__":
    unittest.main()

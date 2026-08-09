from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, call, patch

from scripts.cjk.config import CJKBuildConfig, CJKOutputConfig
from scripts.cjk.static import postprocess_cjk_extended_static_font
from scripts.config.runtime import BuildRuntimeContext, CJKStaticBaseResolution
from scripts.pipeline.cache import (
    CACHE_SCHEMA,
    output_snapshot,
    stage_digest,
    write_cache_record,
)
from scripts.pipeline.cjk_outputs import (
    build_cjk_extended_static_fonts_from_cache,
    build_cjk_extended_variable_outputs,
    cjk_static_base_profiles,
    ensure_cjk_variable_fonts,
)
from scripts.pipeline.orchestrator import BuildPlan, MapleBuildPipeline
from scripts.tests.pipeline_fixtures import (
    make_builtin_entry,
    make_custom_entry,
    make_font_config,
    make_runtime_context,
    make_stage_record,
    write_cjk_profile_outputs,
    write_test_font,
)
from scripts.utils.logging import TaskName

if TYPE_CHECKING:
    from concurrent.futures import Executor


class PipelineCJKOutputsTest(unittest.TestCase):
    def test_cjk_freeze_feature_applies_only_to_static_locale_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entry = make_custom_entry("TC")
            entry.build_config = replace(entry.build_config, freeze_feature="cv99")
            font_config = make_font_config()
            runtime_context = make_runtime_context(Path(tmp))

            with (
                patch("scripts.cjk.static.remove_target_glyph"),
                patch(
                    "scripts.cjk.static.apply_cjk_names",
                    return_value="MapleMono-TC-Regular",
                ),
                patch(
                    "scripts.cjk.static.apply_cjk_width_transform",
                    return_value=False,
                ),
                patch("scripts.cjk.static.apply_cjk_metrics"),
                patch("scripts.cjk.static.apply_binary_features") as apply_features,
                patch("scripts.cjk.static.verify_cjk_widths"),
            ):
                postprocess_cjk_extended_static_font(
                    MagicMock(),
                    entry,
                    font_config,
                    runtime_context,
                    "Regular",
                )

            effective_config = apply_features.call_args.kwargs["config"]
            self.assertEqual(effective_config.feature_freeze["cv99"], "enable")
            self.assertEqual(font_config.feature_freeze["cv99"], "ignore")

    def test_static_cache_resolution_receives_target_styles_and_executor(self) -> None:
        for mode, expected_styles in (
            ("debug", ["Regular", "Italic"]),
            ("least", ["Regular", "Bold", "Italic", "BoldItalic"]),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                font_config = make_font_config()
                font_config.behavior.debug = mode == "debug"
                font_config.behavior.least_styles = mode == "least"
                font_config.nerd_font.enable = False
                target_styles = BuildPlan.from_config(font_config).target_styles
                self.assertEqual(target_styles, expected_styles)
                entry = make_custom_entry("JP")
                runtime_context = make_runtime_context(tmp_path)
                executor = cast("Executor", MagicMock())
                profiles = cjk_static_base_profiles(
                    font_config,
                    runtime_context,
                    entry,
                )
                for profile in profiles:
                    for style in expected_styles:
                        write_test_font(
                            Path(profile.base_dir)
                            / f"{profile.family_name_compact}-{style}.ttf"
                        )
                cache_dir = tmp_path / "cjk-static"
                for style in expected_styles:
                    write_test_font(
                        cache_dir
                        / f"{entry.build_config.naming.static_file_prefix}-{style}.ttf"
                    )
                resolution = CJKStaticBaseResolution(
                    static_dir=cache_dir,
                    static_file_prefix=entry.build_config.naming.static_file_prefix,
                    source_kind="local-static",
                )

                with (
                    patch.object(
                        BuildRuntimeContext,
                        "resolve_cjk_static_base",
                        return_value=resolution,
                    ) as resolve,
                    patch("scripts.pipeline.cjk_outputs.run_process_jobs"),
                ):
                    built = build_cjk_extended_static_fonts_from_cache(
                        entry,
                        font_config,
                        runtime_context,
                        target_styles,
                        executor,
                    )

                self.assertTrue(built)
                self.assertEqual(resolve.call_args.args[1], sorted(expected_styles))
                self.assertIs(resolve.call_args.args[4], executor)

    def test_cjk_stage_logs_grouped_task_before_cache_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.cjk.entries = [make_custom_entry("JP")]
            runtime_context = make_runtime_context(Path(tmp))
            pipeline = MapleBuildPipeline(font_config, runtime_context)
            pipeline._cache_record = {"schema": CACHE_SCHEMA, "stages": {}}
            pipeline._cache_identity_checked = True
            pipeline._cache_identity_valid = True

            manager = MagicMock()
            manager.log_task.return_value = 1.0
            with (
                patch(
                    "scripts.pipeline.orchestrator.build_cjk_extended_static_outputs"
                ) as build_cjk,
                patch.object(pipeline, "_mark_stage_rebuilt"),
                patch("scripts.pipeline.orchestrator.log_task", manager.log_task),
                patch("scripts.pipeline.orchestrator.logger.info", manager.info),
            ):
                pipeline._build_cjk_outputs(cast("Executor", MagicMock()))

            self.assertEqual(
                manager.mock_calls,
                [
                    call.log_task(
                        TaskName.CJK,
                        "Build CJK static outputs (%s)",
                        "JP",
                        task_label="jp",
                        force_separator=True,
                    ),
                    call.info(
                        "Validate stage cache: stage=%s",
                        "jp-static",
                    ),
                    call.info(
                        "Cache miss: stage=%s, reason=missing-record",
                        "jp-static",
                    ),
                ],
            )
            build_cjk.assert_called_once()
            self.assertIsNotNone(build_cjk.call_args.kwargs["started_at"])

    def test_cjk_compatible_profile_misses_build_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.behavior.use_cjk_both = True
            font_config.cjk.entries = [make_custom_entry("CN")]
            runtime_context = make_runtime_context(Path(tmp))
            runtime_context.is_nf_built = True
            pipeline = MapleBuildPipeline(font_config, runtime_context)
            pipeline._cache_record = {"schema": CACHE_SCHEMA, "stages": {}}
            pipeline._cache_identity_checked = True
            pipeline._cache_identity_valid = True

            manager = MagicMock()
            manager.log_task.return_value = 1.0
            with (
                patch(
                    "scripts.pipeline.orchestrator.build_cjk_extended_static_outputs",
                    side_effect=lambda *_args, **_kwargs: write_cjk_profile_outputs(
                        pipeline,
                        _args[4],
                    ),
                ) as build_cjk,
                patch(
                    "scripts.pipeline.orchestrator.log_task",
                    manager.log_task,
                ),
                patch("scripts.pipeline.orchestrator.logger.info", manager.info),
            ):
                pipeline._build_cjk_outputs(cast("Executor", MagicMock()))

            build_cjk.assert_called_once()
            self.assertEqual(build_cjk.call_args.args[4], {"NF-CN", "CN"})
            self.assertEqual(
                manager.mock_calls,
                [
                    call.log_task(
                        TaskName.CJK,
                        "Build CJK static outputs (%s)",
                        "NF-CN, CN",
                        task_label="cn",
                        force_separator=True,
                    ),
                    call.info(
                        "Validate stage cache: stage=%s",
                        "nf-cn-static",
                    ),
                    call.info(
                        "Cache miss: stage=%s, reason=missing-record",
                        "nf-cn-static",
                    ),
                    call.info(
                        "Validate stage cache: stage=%s",
                        "cn-static",
                    ),
                    call.info(
                        "Cache miss: stage=%s, reason=missing-record",
                        "cn-static",
                    ),
                ],
            )
            self.assertEqual(
                set(pipeline._rebuilt_stage_paths),
                {"nf-cn-static", "cn-static"},
            )
            self.assertNotEqual(
                pipeline._stage_cache_identity("nf-cn-static"),
                pipeline._stage_cache_identity("cn-static"),
            )

    def test_cjk_cache_hit_is_excluded_from_grouped_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.behavior.use_cjk_both = True
            font_config.cjk.entries = [make_custom_entry("CN")]
            runtime_context = make_runtime_context(Path(tmp))
            runtime_context.is_nf_built = True
            seeded = MapleBuildPipeline(font_config, runtime_context)
            cn_paths = seeded._cjk_stage_expected_paths("CN")
            write_cjk_profile_outputs(seeded, {"CN"})

            pipeline = MapleBuildPipeline(font_config, runtime_context)
            pipeline._cache_record = {
                "schema": CACHE_SCHEMA,
                "stages": {
                    "cn-static": make_stage_record(seeded, "cn-static", cn_paths),
                },
            }
            pipeline._cache_identity_checked = True
            pipeline._cache_identity_valid = True

            with patch(
                "scripts.pipeline.orchestrator.build_cjk_extended_static_outputs",
                side_effect=lambda *_args, **_kwargs: write_cjk_profile_outputs(
                    pipeline,
                    _args[4],
                ),
            ) as build_cjk:
                pipeline._build_cjk_outputs(cast("Executor", MagicMock()))

            build_cjk.assert_called_once()
            self.assertEqual(build_cjk.call_args.args[4], {"NF-CN"})
            self.assertIn("cn-static", pipeline._validated_stage_records)
            self.assertEqual(set(pipeline._rebuilt_stage_paths), {"nf-cn-static"})

    def test_cjk_different_entries_build_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.cjk.entries = [
                make_custom_entry("HK"),
                make_custom_entry("JP"),
            ]
            runtime_context = make_runtime_context(Path(tmp))
            pipeline = MapleBuildPipeline(font_config, runtime_context)

            with patch(
                "scripts.pipeline.orchestrator.build_cjk_extended_static_outputs",
                side_effect=lambda *_args, **_kwargs: write_cjk_profile_outputs(
                    pipeline,
                    _args[4],
                ),
            ) as build_cjk:
                pipeline._build_cjk_outputs(cast("Executor", MagicMock()))

            self.assertEqual(
                [call.args[4] for call in build_cjk.call_args_list],
                [{"HK"}, {"JP"}],
            )
            self.assertEqual(
                [
                    call.args[0].cjk.entries[0].entry_id
                    for call in build_cjk.call_args_list
                ],
                ["custom:hk", "custom:jp"],
            )

    def test_cjk_group_missing_output_does_not_record_failed_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.use_cjk_both = True
            font_config.cjk.entries = [make_custom_entry("CN")]
            runtime_context = make_runtime_context(Path(tmp))
            runtime_context.is_nf_built = True
            pipeline = MapleBuildPipeline(font_config, runtime_context)

            with (
                patch(
                    "scripts.pipeline.orchestrator.build_cjk_extended_static_outputs",
                    side_effect=lambda *_args, **_kwargs: write_cjk_profile_outputs(
                        pipeline,
                        {"CN"},
                    ),
                ) as build_cjk,
                self.assertRaisesRegex(
                    FileNotFoundError,
                    "Stage nf-cn-static did not produce all expected output files",
                ),
            ):
                pipeline._build_cjk_outputs(cast("Executor", MagicMock()))

            build_cjk.assert_called_once()
            self.assertEqual(build_cjk.call_args.args[4], {"NF-CN", "CN"})
            self.assertNotIn("nf-cn-static", pipeline._rebuilt_stage_paths)
            self.assertIn("cn-static", pipeline._rebuilt_stage_paths)

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

    def test_variable_nf_stage_uses_variable_paths_and_cache_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.cache = True
            font_config.nerd_font.variable = True
            runtime_context = make_runtime_context(Path(tmp))
            pipeline = MapleBuildPipeline(font_config, runtime_context)
            nf_paths = pipeline._nf_variable_stage_expected_paths()
            for nf_path in nf_paths:
                write_test_font(nf_path)
            pipeline._cache_record = {
                "schema": CACHE_SCHEMA,
                "stages": {
                    "nf-variable": {
                        "key": "nf-variable-key",
                        "snapshot": output_snapshot(
                            Path(runtime_context.output_root),
                            "nf-variable",
                            nf_paths,
                        ),
                    }
                },
            }
            pipeline._cache_identity_checked = True
            pipeline._cache_identity_valid = True

            with patch.object(
                pipeline,
                "_stage_cache_identity",
                return_value="nf-variable-key",
            ):
                self.assertTrue(pipeline._validate_recorded_stage("nf-variable"))

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

    def test_variable_cjk_outputs_use_nf_entry_locale_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            font_config.cjk.entries = [make_custom_entry("HK")]
            captured_output_dirs: list[Path] = []

            with patch(
                "scripts.pipeline.cjk_outputs.build_cjk_extended_variable_fonts",
                side_effect=lambda _entry, *_args, **kwargs: (
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
                side_effect=lambda _entry, *_args, **kwargs: (
                    captured_profiles.append(
                        (kwargs["output_locale"], kwargs["include_nerd_font"])
                    )
                    or (Path("regular"), Path("italic"))
                ),
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            self.assertEqual(captured_profiles, [("NF-HK", True), ("HK", False)])

    def test_variable_cjk_outputs_use_nfmono_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            font_config = make_font_config()
            font_config.nerd_font.mono = True
            font_config.cjk.entries = [make_custom_entry("HK")]
            captured_output_dirs: list[str] = []

            with patch(
                "scripts.pipeline.cjk_outputs.build_cjk_extended_variable_fonts",
                side_effect=lambda _entry, *_args, **kwargs: (
                    captured_output_dirs.append(kwargs["output_locale"])
                    or (Path("regular"), Path("italic"))
                ),
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            self.assertEqual(captured_output_dirs, ["NFMono-HK"])

    def test_static_cjk_profiles_use_nfpropo_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            runtime_context.is_nf_built = True
            font_config = make_font_config()
            font_config.nerd_font.propo = True
            entry = make_custom_entry("HK")

            profiles = cjk_static_base_profiles(font_config, runtime_context, entry)

            self.assertEqual(
                [profile.output_locale for profile in profiles], ["NFPropo-HK"]
            )
            self.assertEqual(profiles[0].base_dir, runtime_context.output_nf)

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


if __name__ == "__main__":
    unittest.main()

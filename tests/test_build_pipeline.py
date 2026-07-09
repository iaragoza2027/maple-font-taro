from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from source.py.build.config import CJKCommonBuildOptions, ResolvedCJKBuildEntry
from source.py.build.pipeline import (
    MapleBuildPipeline,
    build_cjk_extended_variable_outputs,
    collect_build_files,
    prune_build_files,
)
from source.py.build.resolver import BuildConfigResolver, BuildRuntimeContext
from source.py.cjk.config import CJKBuildConfig, CJKSourceConfig
from source.py.cjk.presets import build_preset_config, get_preset


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


def make_builtin_entry(locale: str = "cn") -> ResolvedCJKBuildEntry:
    return ResolvedCJKBuildEntry(
        entry_id=locale,
        locale_name=get_preset(locale).family_suffix,
        build_config=build_preset_config(locale),
        common_options=CJKCommonBuildOptions(),
        is_builtin=True,
        preset_id=locale,  # type: ignore[arg-type]
        preset_spec=get_preset(locale),  # type: ignore[arg-type]
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
    def test_build_runs_full_static_branch_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_config = make_font_config()
            font_config.behavior.archive = True
            font_config.behavior.formats = ["woff2"]
            font_config.cjk.entries = [make_builtin_entry("cn")]
            runtime_context = make_runtime_context(Path(tmp))
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
                        "write_build_record",
                        side_effect=lambda: events.append("record"),
                    ):
                        with patch.object(
                            MapleBuildPipeline,
                            "archive_outputs",
                            side_effect=lambda: events.append("archive"),
                        ):
                            with patch.object(
                                MapleBuildPipeline,
                                "finish_build",
                                side_effect=lambda: events.append("finish"),
                            ):
                                with patch(
                                    "source.py.build.pipeline.build_variable_fonts",
                                    side_effect=lambda *_: events.append("variable"),
                                ):
                                    with patch(
                                        "source.py.build.pipeline.build_base_fonts",
                                        side_effect=lambda *_: events.append("static-base"),
                                    ):
                                        with patch(
                                            "source.py.build.pipeline.build_nerd_fonts",
                                            side_effect=lambda *_: events.append("nf"),
                                        ):
                                            with patch(
                                                "source.py.build.pipeline.build_cjk_extended_static_outputs",
                                                side_effect=lambda *_: events.append("cjk-static"),
                                            ):
                                                with patch(
                                                    "source.py.build.pipeline.cleanup_unselected_base_formats",
                                                    side_effect=lambda *_: events.append("cleanup"),
                                                ):
                                                    pipeline.build()

            self.assertEqual(
                events,
                [
                    "prepare",
                    "start",
                    "variable",
                    "static-base",
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
                                    "source.py.build.pipeline.build_variable_fonts"
                                ) as build_variable_mock:
                                    with patch(
                                        "source.py.build.pipeline.build_base_fonts"
                                    ) as build_base_mock:
                                        with patch(
                                            "source.py.build.pipeline.build_nerd_fonts"
                                        ) as build_nf_mock:
                                            with patch(
                                                "source.py.build.pipeline.build_cjk_extended_static_outputs"
                                            ) as build_cjk_mock:
                                                pipeline.build()

            self.assertEqual(events, ["prepare", "start", "reuse", "record", "finish"])
            build_variable_mock.assert_not_called()
            build_base_mock.assert_not_called()
            build_nf_mock.assert_not_called()
            build_cjk_mock.assert_not_called()

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
                "source.py.build.pipeline.read_font_vertical_metric",
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
                "source.py.build.pipeline.build_cjk_extended_variable_fonts",
                side_effect=lambda entry, *_args: captured_output_dirs.append(_args[-1]) or None,
            ):
                build_cjk_extended_variable_outputs(font_config, runtime_context)

            self.assertEqual(
                captured_output_dirs,
                [Path(runtime_context.output_dir) / "Variable-HK"],
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

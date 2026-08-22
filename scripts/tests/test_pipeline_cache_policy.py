from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.cjk.config import CJKBuildConfig, CJKOutputConfig
from scripts.pipeline.orchestrator import MapleBuildPipeline
from scripts.tests.pipeline_fixtures import (
    make_builtin_entry,
    make_custom_entry,
    make_font_config,
    make_runtime_context,
    write_test_font,
)

if TYPE_CHECKING:
    from scripts.config.base import (
        BuildFormatId,
    )


class PipelineCachePolicyTest(unittest.TestCase):
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
            designspace = source_dir / "MapleMono.designspace"
            italic_designspace = source_dir / "MapleMono-Italic.designspace"
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


if __name__ == "__main__":
    unittest.main()

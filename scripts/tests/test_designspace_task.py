from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument

from scripts.font_ops.constant import INSTANCE_WEIGHT_MAPPING
from scripts.font_ops.glyphs import (
    prepare_designspace_source,
)
from scripts.task.designspace import (
    SourceCompatibilityError,
    convert_glyphs_source,
    generate_designspaces,
    prepare_static_source,
    write_designspace_source,
)
from scripts.tests.test_font_generation import write_glyphs_fixture


class DesignspaceTaskTest(unittest.TestCase):
    def test_italic_filename_produces_unique_master_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "Fixture-Italic.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )

            converted = convert_glyphs_source(source_path)

            self.assertEqual(converted.style, "italic")
            self.assertEqual(
                [source.styleName for source in converted.designspace.sources],
                ["ThinItalic", "Italic", "ExtraBoldItalic"],
            )
            self.assertEqual(
                [source.filename for source in converted.designspace.sources],
                [
                    "Fixture-ThinItalic.ufo",
                    "Fixture-Italic.ufo",
                    "Fixture-ExtraBoldItalic.ufo",
                ],
            )

    def test_task_generates_regular_and_italic_designspace_ufo_trees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "exports"
            output_dir = root / "generated"
            source_dir.mkdir()
            layers: dict[str, tuple[str, ...]] = {
                ".notdef": ("Thin", "Regular", "ExtraBold")
            }
            write_glyphs_fixture(source_dir / "Fixture.glyphs", layers)
            write_glyphs_fixture(source_dir / "Fixture-Italic.glyphs", layers)

            with patch(
                "scripts.task.designspace.SOURCE_ISSUE_REPORT",
                root / "fonts" / "source-issues.json",
            ):
                generated = generate_designspaces(source_dir, output_dir)

            self.assertEqual(len(generated), 8)
            self.assertTrue(all(path.exists() for path in generated))
            italic = DesignSpaceDocument.fromfile(
                output_dir / "Fixture-Italic.designspace"
            )
            self.assertEqual(
                [Path(source.filename or "").name for source in italic.sources],
                [
                    "Fixture-ThinItalic.ufo",
                    "Fixture-Italic.ufo",
                    "Fixture-ExtraBoldItalic.ufo",
                ],
            )
            prepared = prepare_designspace_source(
                output_dir / "Fixture-Italic.designspace",
                "italic",
                weight_mapping=INSTANCE_WEIGHT_MAPPING,
            )
            default_source = prepared.designspace.findDefault()
            self.assertIsNotNone(default_source)
            assert default_source is not None
            self.assertEqual(default_source.styleName, "Italic")

    def test_build_preparation_loads_ufo_and_applies_current_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            converted = convert_glyphs_source(source_path)
            static_source = prepare_static_source(converted)
            designspace_path = write_designspace_source(
                static_source,
                root / "generated",
                "Fixture.designspace",
            )

            prepared = prepare_designspace_source(
                designspace_path,
                "regular",
                weight_mapping={**INSTANCE_WEIGHT_MAPPING, "regular": 400},
                line_height=1.2,
            )

            axis = prepared.designspace.axes[0]
            self.assertIsInstance(axis, AxisDescriptor)
            assert isinstance(axis, AxisDescriptor)
            self.assertEqual(
                (axis.minimum, axis.default, axis.maximum),
                (100, 400, 800),
            )
            self.assertEqual(prepared.vertical_metric, (800, -200))
            for source in prepared.designspace.sources:
                assert source.font is not None
                self.assertEqual(source.font.info.openTypeHheaAscender, 960)
                self.assertEqual(source.font.info.openTypeHheaDescender, -240)

    def test_missing_generated_source_points_to_generation_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "Missing.designspace"

            with self.assertRaisesRegex(
                FileNotFoundError,
                "task.py designspace",
            ):
                prepare_designspace_source(missing, "regular")

    def test_invalid_export_preserves_generated_sources_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "exports"
            output_dir = root / "generated"
            report_path = root / "fonts" / "source-issues.json"
            source_dir.mkdir()
            source_path = source_dir / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            with patch("scripts.task.designspace.SOURCE_ISSUE_REPORT", report_path):
                generate_designspaces(source_dir, output_dir)
            designspace_path = output_dir / "Fixture.designspace"
            original_designspace = designspace_path.read_bytes()

            write_glyphs_fixture(source_path, {"orphan": ("Thin",)})
            with (
                patch("scripts.task.designspace.SOURCE_ISSUE_REPORT", report_path),
                self.assertRaises(SourceCompatibilityError),
            ):
                generate_designspaces(source_dir, output_dir)

            self.assertEqual(designspace_path.read_bytes(), original_designspace)
            self.assertTrue(report_path.is_file())

    def test_generation_removes_obsolete_referenced_ufo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "exports"
            output_dir = root / "generated"
            source_dir.mkdir()
            source_path = source_dir / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            with patch(
                "scripts.task.designspace.SOURCE_ISSUE_REPORT",
                root / "fonts" / "source-issues.json",
            ):
                generate_designspaces(source_dir, output_dir)

            designspace_path = output_dir / "Fixture.designspace"
            designspace = DesignSpaceDocument.fromfile(designspace_path)
            thin_path = output_dir / "Fixture-Thin.ufo"
            stale_path = output_dir / "Fixture-Stale.ufo"
            thin_path.rename(stale_path)
            designspace.sources[0].path = str(stale_path.resolve())
            designspace.write(designspace_path)

            with patch(
                "scripts.task.designspace.SOURCE_ISSUE_REPORT",
                root / "fonts" / "source-issues.json",
            ):
                generate_designspaces(source_dir, output_dir)

            self.assertFalse(stale_path.exists())
            self.assertTrue(thin_path.is_dir())


if __name__ == "__main__":
    unittest.main()

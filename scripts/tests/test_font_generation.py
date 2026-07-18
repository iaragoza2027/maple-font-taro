from __future__ import annotations

import tempfile
import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from glyphsLib import load
from glyphsLib.classes import (
    GSComponent,
    GSFeature,
    GSFont,
    GSFontMaster,
    GSGlyph,
    GSLayer,
    GSNode,
    GSPath,
)
from fontTools.ttLib import TTFont

from scripts.build.config import ResolvedBuildConfig
from scripts.feature.apply import patch_font_feature
from scripts.font.generation import (
    SourceCompatibilityError,
    generate_variable_font,
    prepare_glyphs_variable_source,
    validate_source_reports,
    write_source_issue_report,
)
from scripts.font.operations import add_ital_axis_to_stat


def write_glyphs_fixture(
    path: Path,
    glyph_layers: dict[str, tuple[str, ...]],
) -> None:
    font = GSFont()
    font.familyName = "Fixture"
    masters: dict[str, GSFontMaster] = {}
    for name, weight in (("Thin", 100), ("Regular", 400), ("ExtraBold", 800)):
        master = GSFontMaster()
        master.name = name
        master.weightValue = weight
        font.masters.append(master)
        masters[name] = master

    for glyph_name, layer_names in glyph_layers.items():
        glyph = GSGlyph(glyph_name)
        for layer_name in layer_names:
            master = masters[layer_name]
            layer = GSLayer()
            layer.layerId = master.id
            layer.associatedMasterId = master.id
            layer.width = 600
            glyph.layers.append(layer)
        font.glyphs.append(glyph)

    font.save(path)


class GlyphsVariableSourceTest(unittest.TestCase):
    def test_regular_layer_is_reused_without_creating_an_issue_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "Fixture.glyphs"
            write_glyphs_fixture(source_path, {"A.bg": ("Regular",)})

            prepared = prepare_glyphs_variable_source(source_path, "regular")

            self.assertEqual(prepared.errors, ())
            for source in prepared.designspace.sources:
                assert source.font is not None
                self.assertIn("A.bg", source.font)
            self.assertIsNone(
                write_source_issue_report((prepared,), tmp_path / "fonts")
            )

    def test_missing_regular_layer_is_a_fatal_source_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "Fixture.glyphs"
            write_glyphs_fixture(source_path, {"orphan": ("Thin",)})

            prepared = prepare_glyphs_variable_source(source_path, "regular")

            self.assertEqual(
                prepared.errors,
                (
                    {
                        "glyph": "orphan",
                        "kind": "missing_regular_master_layer",
                        "available_masters": ["Thin"],
                        "missing_masters": ["Regular", "ExtraBold"],
                    },
                ),
            )

    def test_issue_report_contains_all_glyphs_without_console_listing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            regular_path = tmp_path / "Regular.glyphs"
            italic_path = tmp_path / "Italic.glyphs"
            write_glyphs_fixture(
                regular_path,
                {"B.bg": ("Thin",), "A.bg": ("Thin",)},
            )
            write_glyphs_fixture(italic_path, {"orphan": ("Thin",)})
            prepared = (
                prepare_glyphs_variable_source(regular_path, "regular"),
                prepare_glyphs_variable_source(italic_path, "italic"),
            )

            console = StringIO()
            with redirect_stdout(console):
                report_path = write_source_issue_report(prepared, tmp_path / "fonts")

            self.assertEqual(report_path, tmp_path / "fonts" / "source-issues.json")
            assert report_path is not None
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [item["glyph"] for item in report["regular"]["errors"]],
                ["A.bg", "B.bg"],
            )
            self.assertEqual(report["regular"]["reused_regular_master_layers"], [])
            self.assertEqual(
                [item["glyph"] for item in report["italic"]["errors"]],
                ["orphan"],
            )
            self.assertNotIn("A.bg", console.getvalue())
            self.assertNotIn("orphan", console.getvalue())

    def test_regular_and_italic_errors_are_aggregated_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            regular_path = tmp_path / "Regular.glyphs"
            italic_path = tmp_path / "Italic.glyphs"
            write_glyphs_fixture(regular_path, {"regularOrphan": ("Thin",)})
            write_glyphs_fixture(italic_path, {"italicOrphan": ("ExtraBold",)})

            reports = (
                generate_variable_font(
                    regular_path,
                    "regular",
                    tmp_path / "regular.ttf",
                ),
                generate_variable_font(
                    italic_path,
                    "italic",
                    tmp_path / "italic.ttf",
                ),
            )
            with self.assertRaises(SourceCompatibilityError):
                validate_source_reports(reports, tmp_path / "fonts")

            report = json.loads(
                (tmp_path / "fonts" / "source-issues.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [item["glyph"] for item in report["regular"]["errors"]],
                ["regularOrphan"],
            )
            self.assertEqual(
                [item["glyph"] for item in report["italic"]["errors"]],
                ["italicOrphan"],
            )

    def test_clean_sources_remove_a_stale_issue_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {"A": ("Thin", "Regular", "ExtraBold")},
            )
            output_dir = tmp_path / "fonts"
            output_dir.mkdir()
            stale_report = output_dir / "source-issues.json"
            stale_report.write_text("stale", encoding="utf-8")

            report_path = write_source_issue_report(
                (prepare_glyphs_variable_source(source_path, "regular"),),
                output_dir,
            )

            self.assertIsNone(report_path)
            self.assertFalse(stale_report.exists())

    def test_incompatible_components_are_reported_without_console_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {
                    "baseOne": ("Thin", "Regular", "ExtraBold"),
                    "baseTwo": ("Thin", "Regular", "ExtraBold"),
                    "target": ("Thin", "Regular", "ExtraBold"),
                },
            )
            with source_path.open(encoding="utf-8") as source_file:
                font = load(source_file)
            target = font.glyphs["target"]
            for layer in target.layers:
                component_name = (
                    "baseTwo"
                    if layer.associatedMasterId == font.masters[-1].id
                    else "baseOne"
                )
                layer.components.append(GSComponent(component_name))
            font.save(source_path)

            prepared = prepare_glyphs_variable_source(source_path, "regular")

            self.assertEqual(
                prepared.errors,
                (
                    {
                        "glyph": "target",
                        "kind": "incompatible_masters",
                        "details": [
                            "component 0 base glyph: "
                            "Thin=baseOne, Regular=baseOne, ExtraBold=baseTwo"
                        ],
                    },
                ),
            )

    def test_incompatible_contours_are_reported_for_every_glyph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {
                    "first": ("Thin", "Regular", "ExtraBold"),
                    "second": ("Thin", "Regular", "ExtraBold"),
                },
            )
            with source_path.open(encoding="utf-8") as source_file:
                font = load(source_file)
            for glyph_name in ("first", "second"):
                layer = font.glyphs[glyph_name].layers[font.masters[-1].id]
                contour = GSPath()
                contour.nodes.extend(
                    (
                        GSNode((0, 0)),
                        GSNode((100, 0)),
                        GSNode((100, 100)),
                        GSNode((0, 100)),
                    )
                )
                contour.closed = True
                layer.paths.append(contour)
            font.save(source_path)

            prepared = prepare_glyphs_variable_source(source_path, "regular")

            self.assertEqual(
                [(error["glyph"], error["details"]) for error in prepared.errors],
                [
                    ("first", ["number of contours"]),
                    ("second", ["number of contours"]),
                ],
            )

    def test_fontmake_generates_variable_font_with_source_glyph_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "Fixture.glyphs"
            output_path = tmp_path / "Fixture[wght].ttf"
            write_glyphs_fixture(
                source_path,
                {
                    ".notdef": ("Thin", "Regular", "ExtraBold"),
                    "A.alt": ("Thin", "Regular", "ExtraBold"),
                },
            )
            with source_path.open(encoding="utf-8") as source_file:
                font = load(source_file)
            font.features.append(GSFeature("liga", "sub A.alt by A.alt;"))
            font.save(source_path)

            report = generate_variable_font(source_path, "regular", output_path)

            self.assertEqual(report.errors, ())
            generated = TTFont(output_path)
            axis = generated["fvar"].axes[0]
            self.assertEqual(
                (axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue),
                ("wght", 100, 400, 800),
            )
            self.assertIn("A.alt", generated.getGlyphOrder())
            self.assertNotIn("GSUB", generated.keys())

            feature_path = tmp_path / "project.fea"
            feature_path.write_text(
                "feature liga { sub A.alt by A.alt; } liga;",
                encoding="utf-8",
            )
            config = ResolvedBuildConfig()
            config.behavior.apply_fea_file = True
            patch_font_feature(
                config=config,
                font=generated,
                issue_fea_dir=tmp_path,
                is_italic=False,
                is_cn=False,
                is_variable=True,
                is_hinted=False,
                fea_path=str(feature_path),
            )
            self.assertIn("GSUB", generated.keys())

    def test_italic_stat_axis_supports_fontmake_without_axis_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "Fixture.glyphs"
            output_path = tmp_path / "Fixture-Italic[wght].ttf"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            report = generate_variable_font(source_path, "italic", output_path)
            self.assertEqual(report.errors, ())
            generated = TTFont(output_path)

            self.assertIsNone(generated["STAT"].table.AxisValueArray)
            add_ital_axis_to_stat(generated)

            stat = generated["STAT"].table
            self.assertEqual(
                [axis.AxisTag for axis in stat.DesignAxisRecord.Axis],
                ["wght", "ital"],
            )
            self.assertEqual(stat.AxisValueCount, 1)
            self.assertEqual(stat.AxisValueArray.AxisValue[0].Value, 1.0)

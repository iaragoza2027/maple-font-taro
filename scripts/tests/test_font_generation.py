from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from threading import Barrier, current_thread
from typing import TYPE_CHECKING
from unittest.mock import patch

from fontmake.font_project import CFFOptimization, FontProject
from fontTools.designspaceLib import DesignSpaceDocument
from glyphsLib import load
from glyphsLib.classes import (
    GSComponent,
    GSFeature,
    GSFont,
    GSFontMaster,
    GSGlyph,
    GSInstance,
    GSLayer,
    GSNode,
    GSPath,
)
from ufoLib2 import Font as UFOFont

from scripts.config.base import ResolvedConfig
from scripts.feature.apply import apply_binary_features
from scripts.font_ops.constant import INSTANCE_WEIGHT_MAPPING
from scripts.font_ops.fonttools import instantiate_variable_font, load_font
from scripts.font_ops.glyph_transform import SmartWidthThickenFilter
from scripts.font_ops.glyphs import (
    FontmakeBranchJob,
    SourceStyle,
    _fontmake_options,
    compile_fontmake_branches,
    materialize_prepared_source,
    prepare_designspace_source,
)
from scripts.font_ops.names import ensure_variable_instance_names
from scripts.font_ops.opentype import (
    add_ital_axis_to_stat,
    add_weight_axis_values_to_stat,
    alias_codepoints,
)
from scripts.task.designspace import (
    SourceCompatibilityError,
    convert_glyphs_source,
    prepare_static_source,
    validate_source_reports,
    write_designspace_source,
    write_source_issue_report,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


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

    instance = GSInstance()
    instance.name = "Regular"
    instance.weightValue = 400
    font.instances.append(instance)

    for glyph_name, layer_names in glyph_layers.items():
        glyph = GSGlyph(glyph_name)
        if len(glyph_name) == 1:
            glyph.unicode = f"{ord(glyph_name):04X}"
        for layer_name in layer_names:
            master = masters[layer_name]
            layer = GSLayer()
            layer.layerId = master.id
            layer.associatedMasterId = master.id
            layer.width = 600
            glyph.layers.append(layer)
        font.glyphs.append(glyph)

    font.save(path)


def prepare_glyphs_fixture(
    source_path: Path,
    style: SourceStyle,
    target_width: int | None = None,
    original_ref_width: int = 600,
    weight_mapping: dict[str, int] | None = None,
    line_height: float = 1,
):
    prepared = prepare_static_fixture(source_path, style)
    if prepared.errors:
        raise AssertionError(prepared.errors)
    designspace_path = write_designspace_source(
        prepared,
        source_path.parent / f"{source_path.stem}-generated",
        source_path.with_suffix(".designspace").name,
    )
    return prepare_designspace_source(
        designspace_path,
        style,
        target_width=target_width,
        original_ref_width=original_ref_width,
        weight_mapping=weight_mapping,
        line_height=line_height,
    )


def prepare_static_fixture(source_path: Path, style: SourceStyle):
    return prepare_static_source(convert_glyphs_source(source_path, style))


def compile_fixture(
    source_path: Path,
    style: SourceStyle,
    output_path: Path,
) -> None:
    prepared = prepare_glyphs_fixture(source_path, style)
    designspace_path = materialize_prepared_source(
        prepared, output_path.parent / f"{style}-prepared"
    )
    compile_fontmake_branches(
        [
            FontmakeBranchJob(designspace_path, "variable", output_path),
            FontmakeBranchJob(
                designspace_path,
                "ttf",
                output_path.parent / f"{style}-ttf",
                interpolate=True,
            ),
        ]
    )


class DesignspaceVariableSourceTest(unittest.TestCase):
    def assert_ufo_readers_closed(self, fonts: Sequence[UFOFont | None]) -> None:
        for font in fonts:
            self.assertIsNotNone(font)
            assert font is not None
            reader = font._reader
            self.assertIsNotNone(reader)
            assert reader is not None
            self.assertTrue(reader.fs.isclosed())

    def test_prepare_sets_build_metadata_on_every_ufo_master(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )

            prepared = prepare_glyphs_fixture(
                source_path,
                "regular",
                line_height=1.2,
            )

            self.assertEqual(prepared.vertical_metric, (800, -200))
            for source in prepared.designspace.sources:
                assert source.font is not None
                info = source.font.info
                self.assertIs(info.postscriptIsFixedPitch, True)
                self.assertEqual(info.openTypeOS2Panose, [2, 0, 0, 9, 0, 0, 0, 0, 0, 0])
                assert info.openTypeGaspRangeRecords is not None
                self.assertEqual(
                    dict(info.openTypeGaspRangeRecords[0]),
                    {
                        "rangeMaxPPEM": 65535,
                        "rangeGaspBehavior": [0, 1, 2, 3],
                    },
                )
                self.assertEqual(info.openTypeHheaAscender, 960)
                self.assertEqual(info.openTypeHheaDescender, -240)
                self.assertEqual(info.openTypeOS2TypoAscender, 960)
                self.assertEqual(info.openTypeOS2TypoDescender, -240)
                self.assertEqual(info.openTypeOS2WinAscent, 960)
                self.assertEqual(info.openTypeOS2WinDescent, 240)

    def test_materializing_prepared_source_closes_every_ufo_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            prepared = prepare_glyphs_fixture(source_path, "regular")
            fonts = [source.font for source in prepared.designspace.sources]

            materialize_prepared_source(prepared, root / "prepared")

            self.assert_ufo_readers_closed(fonts)
            self.assertTrue(
                all(source.font is None for source in prepared.designspace.sources)
            )

    def test_materialization_failure_closes_every_ufo_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            prepared = prepare_glyphs_fixture(source_path, "regular")
            fonts = [source.font for source in prepared.designspace.sources]

            with (
                patch.object(UFOFont, "save", side_effect=OSError("save failed")),
                self.assertRaisesRegex(OSError, "save failed"),
            ):
                materialize_prepared_source(prepared, root / "prepared")

            self.assert_ufo_readers_closed(fonts)
            self.assertTrue(
                all(source.font is None for source in prepared.designspace.sources)
            )

    def test_designspace_write_failure_closes_every_ufo_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            prepared = prepare_glyphs_fixture(source_path, "regular")
            fonts = [source.font for source in prepared.designspace.sources]

            with (
                patch.object(
                    DesignSpaceDocument,
                    "write",
                    side_effect=OSError("designspace write failed"),
                ),
                self.assertRaisesRegex(OSError, "designspace write failed"),
            ):
                materialize_prepared_source(prepared, root / "prepared")

            self.assert_ufo_readers_closed(fonts)
            self.assertTrue(
                all(source.font is None for source in prepared.designspace.sources)
            )

    def test_preparation_failure_closes_every_opened_ufo_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            static_source = prepare_static_fixture(source_path, "regular")
            designspace_path = write_designspace_source(
                static_source,
                root / "generated",
                "Fixture.designspace",
            )
            designspace = DesignSpaceDocument.fromfile(designspace_path)
            designspace.axes = []
            designspace.write(designspace_path)
            opened_fonts: list[UFOFont] = []
            original_open = UFOFont.open

            def track_open(path):
                font = original_open(path)
                opened_fonts.append(font)
                return font

            with (
                patch.object(UFOFont, "open", side_effect=track_open),
                self.assertRaisesRegex(ValueError, "continuous named wght axis"),
            ):
                prepare_designspace_source(designspace_path, "regular")

            self.assertEqual(len(opened_fonts), 3)
            self.assert_ufo_readers_closed(opened_fonts)

    def test_fontmake_compiles_prepared_variable_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            output_path = root / "Fixture[wght].ttf"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            with source_path.open(encoding="utf-8") as source_file:
                glyphs_font = load(source_file)
            instance = GSInstance()
            instance.name = "ExtraLight"
            instance.weightValue = 200
            glyphs_font.instances.append(instance)
            glyphs_font.save(source_path)

            prepared = prepare_glyphs_fixture(
                source_path,
                "regular",
                weight_mapping={**INSTANCE_WEIGHT_MAPPING, "extralight": 275},
                line_height=1.2,
            )
            designspace_path = materialize_prepared_source(
                prepared,
                root / "prepared",
            )
            compile_fontmake_branches(
                [FontmakeBranchJob(designspace_path, "variable", output_path)]
            )

            generated = load_font(output_path)
            instances = {
                generated["name"].getDebugName(item.subfamilyNameID): item
                for item in generated["fvar"].instances
            }
            os2 = generated.table("OS/2")
            post = generated.table("post")
            self.assertEqual(instances["ExtraLight"].coordinates["wght"], 275)
            self.assertTrue(post.isFixedPitch)
            self.assertEqual(os2.panose.bFamilyType, 2)
            self.assertEqual(os2.panose.bProportion, 9)
            self.assertEqual(generated["gasp"].gaspRange, {65535: 15})
            self.assertEqual(generated["hhea"].ascent, 960)
            self.assertEqual(generated["hhea"].descent, -240)
            self.assertEqual(os2.sTypoAscender, 960)
            self.assertEqual(os2.sTypoDescender, -240)
            self.assertEqual(os2.usWinAscent, 960)
            self.assertEqual(os2.usWinDescent, 240)
            self.assertEqual(generated["hhea"].advanceWidthMax, 600)
            self.assertEqual(os2.xAvgCharWidth, 600)
            self.assertNotEqual(generated["head"].yMax, 960)
            self.assertNotEqual(generated["head"].yMin, -240)
            generated.close()

    def test_static_source_does_not_add_runtime_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {"K": ("Thin", "Regular", "ExtraBold")},
            )

            prepared = prepare_static_fixture(source_path, "regular")

            for source in prepared.designspace.sources:
                assert source.font is not None
                self.assertIn(0x004B, source.font["K"].unicodes)
                self.assertNotIn(0x212A, source.font["K"].unicodes)

    def test_runtime_aliases_include_builtins_and_configured_extras(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            output_path = root / "Fixture[wght].ttf"
            write_glyphs_fixture(
                source_path,
                {
                    ".notdef": ("Thin", "Regular", "ExtraBold"),
                    "K": ("Thin", "Regular", "ExtraBold"),
                },
            )
            compile_fixture(source_path, "regular", output_path)
            font = load_font(output_path)
            try:
                alias_codepoints(font, {0xE000: 0x004B})
                cmap = font.getBestCmap()
                assert cmap is not None
                self.assertEqual(cmap[0x212A], "K")
                self.assertEqual(cmap[0xE000], "K")
            finally:
                font.close()

    def test_regular_layer_is_reused_without_creating_an_issue_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "Fixture.glyphs"
            write_glyphs_fixture(source_path, {"A.bg": ("Regular",)})

            prepared = prepare_static_fixture(source_path, "regular")

            self.assertEqual(prepared.errors, ())
            for source in prepared.designspace.sources:
                assert source.font is not None
                self.assertIn("A.bg", source.font)
            report_path = tmp_path / "fonts" / "source-issues.json"
            with patch("scripts.task.designspace.SOURCE_ISSUE_REPORT", report_path):
                self.assertIsNone(write_source_issue_report((prepared,)))

    def test_missing_regular_layer_is_a_fatal_source_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "Fixture.glyphs"
            write_glyphs_fixture(source_path, {"orphan": ("Thin",)})

            prepared = prepare_static_fixture(source_path, "regular")

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
                prepare_static_fixture(regular_path, "regular"),
                prepare_static_fixture(italic_path, "italic"),
            )

            expected_report = tmp_path / "fonts" / "source-issues.json"
            with (
                patch("scripts.task.designspace.SOURCE_ISSUE_REPORT", expected_report),
                self.assertLogs("scripts", level="INFO") as logs,
            ):
                report_path = write_source_issue_report(prepared)

            self.assertEqual(report_path, expected_report)
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
            self.assertNotIn("A.bg", "\n".join(logs.output))
            self.assertNotIn("orphan", "\n".join(logs.output))

    def test_regular_and_italic_errors_are_aggregated_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            regular_path = tmp_path / "Regular.glyphs"
            italic_path = tmp_path / "Italic.glyphs"
            write_glyphs_fixture(regular_path, {"regularOrphan": ("Thin",)})
            write_glyphs_fixture(italic_path, {"italicOrphan": ("ExtraBold",)})

            reports = (
                prepare_static_fixture(regular_path, "regular"),
                prepare_static_fixture(italic_path, "italic"),
            )
            report_path = tmp_path / "fonts" / "source-issues.json"
            with (
                patch("scripts.task.designspace.SOURCE_ISSUE_REPORT", report_path),
                self.assertRaises(SourceCompatibilityError),
            ):
                validate_source_reports(reports)

            report = json.loads(report_path.read_text(encoding="utf-8"))
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

            with patch("scripts.task.designspace.SOURCE_ISSUE_REPORT", stale_report):
                report_path = write_source_issue_report(
                    (prepare_static_fixture(source_path, "regular"),)
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
            assert target is not None
            master = font.masters[-1]
            assert master is not None
            for layer in target.layers:
                component_name = (
                    "baseTwo" if layer.associatedMasterId == master.id else "baseOne"
                )
                layer.components.append(GSComponent(component_name))
            font.save(source_path)

            prepared = prepare_static_fixture(source_path, "regular")

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
            master = font.masters[-1]
            assert master is not None
            for glyph_name in ("first", "second"):
                glyph = font.glyphs[glyph_name]
                assert glyph is not None
                layer = glyph.layers[master.id]
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

            prepared = prepare_static_fixture(source_path, "regular")

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

            compile_fixture(source_path, "regular", output_path)
            generated = load_font(output_path)
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
            config = ResolvedConfig()
            config.behavior.apply_fea_file = True
            apply_binary_features(
                config=config,
                font=generated,
                issue_fea_dir=tmp_path,
                is_italic=False,
                is_cn=False,
                is_hinted=False,
                fea_path=str(feature_path),
            )
            self.assertIn("GSUB", generated.keys())

    def test_fontmake_compiles_static_ttf_and_source_native_otf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {
                    ".notdef": ("Thin", "Regular", "ExtraBold"),
                    "A": ("Thin", "Regular", "ExtraBold"),
                },
            )
            prepared = prepare_glyphs_fixture(source_path, "regular")

            designspace_path = materialize_prepared_source(prepared, root / "prepared")
            compile_fontmake_branches(
                [
                    FontmakeBranchJob(
                        designspace_path, "variable", root / "variable.ttf"
                    ),
                    FontmakeBranchJob(
                        designspace_path, "ttf", root / "ttf", interpolate=True
                    ),
                    FontmakeBranchJob(
                        designspace_path, "otf", root / "otf", interpolate=True
                    ),
                ]
            )
            ttf = load_font(root / "ttf" / "Fixture-Regular.ttf")
            otf = load_font(root / "otf" / "Fixture-Regular.otf")
            self.assertIn("glyf", ttf.keys())
            self.assertNotIn("CFF ", ttf.keys())
            self.assertEqual(ttf["gasp"].gaspRange, {65535: 15})
            self.assertEqual(ttf.table("maxp").maxZones, 1)
            self.assertFalse({"cvt ", "fpgm", "prep"} & set(ttf.keys()))
            self.assertEqual(
                sum(
                    len(glyph.program.getBytecode())
                    for glyph in ttf["glyf"].glyphs.values()
                    if hasattr(glyph, "program")
                ),
                0,
            )
            self.assertEqual(otf.sfntVersion, "OTTO")
            self.assertIn("CFF ", otf.keys())
            self.assertNotIn("glyf", otf.keys())
            self.assertEqual(ttf.getGlyphOrder(), otf.getGlyphOrder())
            self.assertEqual(
                {name: width for name, (width, _) in ttf["hmtx"].metrics.items()},
                {name: width for name, (width, _) in otf["hmtx"].metrics.items()},
            )
            ttf.close()
            otf.close()

    def test_fontmake_branches_interpolate_and_use_default_subroutinizer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            prepared = prepare_glyphs_fixture(source_path, "regular")
            designspace_path = materialize_prepared_source(prepared, root / "prepared")

            barrier = Barrier(3)
            thread_names: set[str] = set()

            def record_branch(*_args, **_kwargs) -> None:
                thread_names.add(current_thread().name)
                barrier.wait(timeout=2)

            with patch.object(
                FontProject,
                "run_from_designspace",
                autospec=True,
                side_effect=record_branch,
            ) as run_from_designspace:
                compile_fontmake_branches(
                    [
                        FontmakeBranchJob(
                            designspace_path, "variable", root / "variable.ttf"
                        ),
                        FontmakeBranchJob(
                            designspace_path, "ttf", root / "ttf", interpolate=True
                        ),
                        FontmakeBranchJob(
                            designspace_path, "otf", root / "otf", interpolate=True
                        ),
                    ]
                )

            self.assertEqual(run_from_designspace.call_count, 3)
            self.assertEqual(len(thread_names), 3)
            designspace_paths = {
                call.args[1] for call in run_from_designspace.call_args_list
            }
            self.assertEqual(len(designspace_paths), 1)
            otf_call = next(
                call
                for call in run_from_designspace.call_args_list
                if call.kwargs["output"] == ("otf",)
            )
            self.assertIs(otf_call.kwargs["interpolate"], True)
            self.assertEqual(
                otf_call.kwargs["optimize_cff"],
                CFFOptimization.SUBROUTINIZE,
            )
            self.assertNotIn("subroutinizer", otf_call.kwargs)

    def test_fontmake_accepts_static_filter_without_filtering_variable_names(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "Fixture.glyphs"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            prepared = prepare_glyphs_fixture(source_path, "regular")
            designspace_path = materialize_prepared_source(
                prepared,
                root / "prepared",
            )

            compile_fontmake_branches(
                [
                    FontmakeBranchJob(
                        designspace_path,
                        "variable",
                        root / "variable.ttf",
                    ),
                    FontmakeBranchJob(
                        designspace_path,
                        "ttf",
                        root / "ttf",
                        interpolate=r".* Regular",
                    ),
                ]
            )

            self.assertEqual(
                sorted(path.name for path in (root / "ttf").glob("*.ttf")),
                ["Fixture-Regular.ttf"],
            )
            variable_font = load_font(root / "variable.ttf")
            try:
                instance_names = {
                    variable_font["name"].getDebugName(instance.subfamilyNameID)
                    for instance in variable_font["fvar"].instances
                }
            finally:
                variable_font.close()
            self.assertEqual(instance_names, {"Regular"})

    def test_width_thickening_is_a_post_conversion_filter(self) -> None:
        width_transform = (500, 600)
        for output in ("variable", "ttf", "otf"):
            with self.subTest(output=output):
                job = FontmakeBranchJob(
                    Path("Fixture.designspace"),
                    output,
                    Path("output.ttf"),
                    interpolate=output != "variable",
                    width_transform=width_transform,
                )
                filters = _fontmake_options(job)["filters"]
                width_filter = next(
                    item
                    for item in filters
                    if isinstance(item, SmartWidthThickenFilter)
                )
                self.assertFalse(width_filter.pre)
                self.assertEqual(width_filter.options.target_width, 500)
                self.assertEqual(width_filter.options.original_ref_width, 600)

    def test_slim_width_compiles_production_variable_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / "MapleMonoSL[wght].ttf"
            prepared = prepare_designspace_source(
                "source/MapleMono[wght].designspace",
                "regular",
                target_width=500,
                original_ref_width=600,
            )
            designspace_path = materialize_prepared_source(
                prepared,
                root / "prepared",
            )

            compile_fontmake_branches(
                [
                    FontmakeBranchJob(
                        designspace_path,
                        "variable",
                        output_path,
                        width_transform=(500, 600),
                    )
                ]
            )

            variable_font = load_font(output_path)
            try:
                self.assertEqual(len(variable_font["fvar"].instances), 8)
                add_weight_axis_values_to_stat(variable_font)
                stat_values = variable_font["STAT"].table.AxisValueArray.AxisValue
                self.assertEqual(len(stat_values), 8)
                self.assertEqual(
                    {
                        variable_font["name"].getDebugName(value.ValueNameID)
                        for value in stat_values
                    },
                    {
                        "Thin",
                        "ExtraLight",
                        "Light",
                        "Regular",
                        "Medium",
                        "SemiBold",
                        "Bold",
                        "ExtraBold",
                    },
                )
                for coordinate in (100, 400, 800):
                    instance = instantiate_variable_font(
                        variable_font,
                        {"wght": coordinate},
                    )
                    try:
                        widths = {
                            width for width, _ in instance["hmtx"].metrics.values()
                        }
                        self.assertLessEqual(widths, {0, 500})
                    finally:
                        instance.close()
            finally:
                variable_font.close()

    def test_italic_stat_axis_supports_fontmake_without_axis_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "Fixture.glyphs"
            output_path = tmp_path / "Fixture-Italic[wght].ttf"
            write_glyphs_fixture(
                source_path,
                {".notdef": ("Thin", "Regular", "ExtraBold")},
            )
            compile_fixture(source_path, "italic", output_path)
            generated = load_font(output_path)

            self.assertIsNone(generated["STAT"].table.AxisValueArray)
            ensure_variable_instance_names(generated, italic=True)
            add_weight_axis_values_to_stat(generated)
            axis_value_array = generated["STAT"].table.AxisValueArray
            if axis_value_array is None:
                self.fail("Weight STAT values were not created")
            self.assertEqual(
                generated["name"].getDebugName(
                    axis_value_array.AxisValue[0].ValueNameID
                ),
                "Italic",
            )
            add_weight_axis_values_to_stat(generated, italic=True)

            stat = generated["STAT"].table
            self.assertEqual(stat.AxisValueCount, 1)
            self.assertEqual(
                generated["name"].getDebugName(
                    generated["fvar"].instances[0].subfamilyNameID
                ),
                "Italic",
            )
            self.assertEqual(
                [
                    generated["name"].getDebugName(value.ValueNameID)
                    for value in stat.AxisValueArray.AxisValue
                ],
                ["Regular"],
            )

            add_ital_axis_to_stat(generated)

            self.assertEqual(
                [axis.AxisTag for axis in stat.DesignAxisRecord.Axis],
                ["wght", "ital"],
            )
            self.assertEqual(stat.AxisValueCount, 2)
            self.assertEqual(stat.AxisValueArray.AxisValue[-1].Value, 1.0)

from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, cast

from fontTools.pens.cu2quPen import Cu2QuMultiPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable

from scripts.cjk.outlines import (
    as_fonttools_glyph_mapping,
    install_glyf_tables,
    record_glyph_commands,
    replay_multi_glyph_commands,
)
from scripts.tests.cjk_font_fixtures import (
    GLYPH_ORDER,
    build_test_font,
    glyph_coordinates,
    roundtrip_font,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


class CJKOutlineOperationsTest(unittest.TestCase):
    def test_replay_compatible_real_glyph_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fonts = [
                build_test_font(root / f"master-{width}.ttf", box_width=width)
                for width in (240, 320, 420)
            ]
            recordings = [
                record_glyph_commands(font.getGlyphSet(), "box") for font in fonts
            ]
            pens = [TTGlyphPen(None) for _ in fonts]

            replay_multi_glyph_commands(
                "box",
                recordings,
                Cu2QuMultiPen(pens, max_err=1.0, reverse_direction=False),
            )
            converted = [pen.glyph() for pen in pens]

            for font, glyph in zip(fonts, converted, strict=False):
                coordinates, _, _ = glyph.getCoordinates(font["glyf"])
                self.assertEqual(
                    [
                        (round(x), round(y))
                        for x, y in cast("Iterable[tuple[float, float]]", coordinates)
                    ],
                    glyph_coordinates(font, "box"),
                )
                font.close()

    def test_replay_rejects_operation_mismatch_from_real_glyphs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            linear = build_test_font(root / "linear.ttf")
            curved = build_test_font(root / "curved.ttf", curved_box=True)
            self.addCleanup(linear.close)
            self.addCleanup(curved.close)
            recordings = [
                record_glyph_commands(font.getGlyphSet(), "box")
                for font in (linear, curved)
            ]

            with self.assertRaisesRegex(
                ValueError, r"command #1 lineTo/1 != qCurveTo/"
            ):
                replay_multi_glyph_commands(
                    "box",
                    recordings,
                    Cu2QuMultiPen(
                        [TTGlyphPen(None), TTGlyphPen(None)],
                        max_err=1.0,
                        reverse_direction=False,
                    ),
                )

    def test_replay_rejects_component_mismatch_from_real_glyphs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            box_component = build_test_font(root / "box-component.ttf")
            cjk_component = build_test_font(
                root / "cjk-component.ttf", component_target="cjk"
            )
            self.addCleanup(box_component.close)
            self.addCleanup(cjk_component.close)
            recordings = [
                record_glyph_commands(font.getGlyphSet(), "box.component")
                for font in (box_component, cjk_component)
            ]
            glyph_sets = [
                as_fonttools_glyph_mapping(font.getGlyphSet())
                for font in (box_component, cjk_component)
            ]

            with self.assertRaisesRegex(ValueError, "component mismatch box != cjk"):
                replay_multi_glyph_commands(
                    "box.component",
                    recordings,
                    Cu2QuMultiPen(
                        [TTGlyphPen(glyph_set) for glyph_set in glyph_sets],
                        max_err=1.0,
                        reverse_direction=False,
                    ),
                )

    def test_install_glyf_tables_replaces_cff_and_roundtrips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font = build_test_font(root / "source.ttf")
            expected_coordinates = {
                glyph_name: glyph_coordinates(font, glyph_name)
                for glyph_name in GLYPH_ORDER
            }
            converted_glyphs = {
                glyph_name: (deepcopy(font["glyf"][glyph_name]),)
                for glyph_name in GLYPH_ORDER
            }
            font["CFF "] = newTable("CFF ")
            font["CFF2"] = newTable("CFF2")

            install_glyf_tables([font], GLYPH_ORDER, converted_glyphs)
            installed = roundtrip_font(font, root / "installed.ttf")
            self.addCleanup(installed.close)

            self.assertIn("glyf", installed)
            self.assertIn("loca", installed)
            self.assertNotIn("CFF ", installed)
            self.assertNotIn("CFF2", installed)
            self.assertEqual(installed.getGlyphOrder(), GLYPH_ORDER)
            self.assertEqual(installed["maxp"].numGlyphs, len(GLYPH_ORDER))
            for glyph_name in GLYPH_ORDER:
                self.assertEqual(
                    glyph_coordinates(installed, glyph_name),
                    expected_coordinates[glyph_name],
                )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fontTools.pens.ttGlyphPen import TTGlyphPen

from scripts.font_ops.opentype import remove_target_glyph
from scripts.tests.cjk_font_fixtures import build_test_font, glyph_coordinates


def outlined_notdef():
    pen = TTGlyphPen(None)
    pen.moveTo((100, 0))
    pen.lineTo((500, 0))
    pen.lineTo((500, 700))
    pen.lineTo((100, 700))
    pen.closePath()
    return pen.glyph()


class OpenTypeFontOpsTest(unittest.TestCase):
    def test_removing_target_glyph_preserves_notdef_outline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font = build_test_font(Path(tmp) / "fixture.ttf")
            try:
                font["glyf"][".notdef"] = outlined_notdef()
                expected_coordinates = glyph_coordinates(font, ".notdef")

                remove_target_glyph(font, ".component")

                self.assertNotIn("box.component", font.getGlyphOrder())
                self.assertEqual(font["glyf"][".notdef"].numberOfContours, 1)
                self.assertEqual(
                    glyph_coordinates(font, ".notdef"), expected_coordinates
                )
            finally:
                font.close()


if __name__ == "__main__":
    unittest.main()

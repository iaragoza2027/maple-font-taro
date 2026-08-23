from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables.ttProgram import Program

from scripts.font_ops.merge import merge_ttfonts
from scripts.tests.cjk_font_fixtures import build_test_font


def overlapping_glyph():
    pen = TTGlyphPen(None)
    for x_min, x_max in ((50, 300), (200, 450)):
        pen.moveTo((x_min, 0))
        pen.lineTo((x_max, 0))
        pen.lineTo((x_max, 500))
        pen.lineTo((x_min, 500))
        pen.closePath()
    return pen.glyph()


class MergeTTFontsTest(unittest.TestCase):
    def write_base_and_extra(self, root: Path) -> tuple[Path, Path]:
        base_path = root / "base.ttf"
        extra_path = root / "extra.ttf"
        base = build_test_font(base_path, glyph_order=[".notdef", "box"])
        program = Program()
        program.fromBytecode(b"\x00")
        base["glyf"]["box"].program = program
        base.recalcTimestamp = False
        base.save(base_path)
        base.close()

        extra = build_test_font(extra_path, glyph_order=[".notdef", "box", "cjk"])
        extra["glyf"]["cjk"] = overlapping_glyph()
        extra["hmtx"].metrics["cjk"] = (600, 50)
        extra.recalcTimestamp = False
        extra.save(extra_path)
        extra.close()
        return base_path, extra_path

    def test_does_not_remove_extra_overlaps_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_path, extra_path = self.write_base_and_extra(Path(tmp))
            with patch("scripts.font_ops.merge.remove_overlaps") as remove:
                merged = merge_ttfonts(str(base_path), str(extra_path))
            try:
                remove.assert_not_called()
            finally:
                merged.close()

    def test_removes_only_new_extra_glyph_overlaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_path, extra_path = self.write_base_and_extra(Path(tmp))
            with patch("scripts.font_ops.merge.remove_overlaps") as remove:
                merged = merge_ttfonts(
                    str(base_path), str(extra_path), remove_extra_overlaps=True
                )
            try:
                remove.assert_called_once()
                self.assertEqual(remove.call_args.args[1], ["cjk"])
                self.assertEqual(merged["glyf"]["box"].program.getBytecode(), b"\x00")
            finally:
                merged.close()

    def test_removes_overlapping_extra_outlines_without_changing_base_hinting(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_path, extra_path = self.write_base_and_extra(Path(tmp))
            merged = merge_ttfonts(
                str(base_path), str(extra_path), remove_extra_overlaps=True
            )
            try:
                self.assertEqual(merged["glyf"]["cjk"].numberOfContours, 1)
                self.assertEqual(merged["glyf"]["box"].program.getBytecode(), b"\x00")
            finally:
                merged.close()


if __name__ == "__main__":
    unittest.main()

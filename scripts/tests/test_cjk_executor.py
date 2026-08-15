from __future__ import annotations

import unittest
from typing import TYPE_CHECKING, cast

from scripts.cjk.outlines import (
    detect_outline_format,
)

if TYPE_CHECKING:
    from scripts.font_ops.fonttools import TTFont


class CJKOutlineDetectionTest(unittest.TestCase):
    def make_font(self, *tables: str) -> TTFont:
        return cast("TTFont", {table: object() for table in tables})

    def test_detects_glyf_outline(self) -> None:
        self.assertEqual(
            detect_outline_format(self.make_font("glyf"), "source.ttf"),
            "glyf",
        )

    def test_detects_cff2_outline(self) -> None:
        self.assertEqual(
            detect_outline_format(self.make_font("CFF2"), "source.otf"),
            "cff2",
        )

    def test_rejects_static_cff_outline(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "static CFF.*source.otf.*variable font containing glyf or CFF2",
        ):
            detect_outline_format(self.make_font("CFF "), "source.otf")

    def test_rejects_missing_outline(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "no supported outlines.*source.bin.*exactly one of glyf or CFF2",
        ):
            detect_outline_format(self.make_font("name"), "source.bin")

    def test_rejects_ambiguous_variable_outlines(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "both glyf and CFF2.*source.ttf.*exactly one",
        ):
            detect_outline_format(
                self.make_font("glyf", "CFF2"),
                "source.ttf",
            )


if __name__ == "__main__":
    unittest.main()

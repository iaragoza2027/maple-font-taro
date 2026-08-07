from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.font_ops.fonttools import load_font


class LoadFontTest(unittest.TestCase):
    @patch("scripts.font_ops.fonttools.TTFont")
    def test_loads_font_into_memory_with_deterministic_timestamps(
        self, ttfont: MagicMock
    ) -> None:
        font_path = Path("fixture.ttf")

        result = load_font(font_path)

        self.assertIs(result, ttfont.return_value)
        ttfont.assert_called_once_with(
            font_path,
            lazy=False,
            recalcTimestamp=False,
        )
        ttfont.return_value.ensureDecompiled.assert_not_called()

    @patch("scripts.font_ops.fonttools.TTFont")
    def test_decompiles_all_tables_when_requested(self, ttfont: MagicMock) -> None:
        result = load_font("fixture.ttf", decompile=True)

        self.assertIs(result, ttfont.return_value)
        ttfont.return_value.ensureDecompiled.assert_called_once_with()

    @patch("scripts.font_ops.fonttools.TTFont")
    def test_closes_font_when_decompilation_fails(self, ttfont: MagicMock) -> None:
        ttfont.return_value.ensureDecompiled.side_effect = ValueError("invalid table")

        with self.assertRaisesRegex(ValueError, "invalid table"):
            load_font("fixture.ttf", decompile=True)

        ttfont.return_value.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.font_ops.merge import merge_ttfonts

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FontOpsBoundaryTest(unittest.TestCase):
    def test_font_ops_does_not_load_cjk_or_build_runtime_modules(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import scripts.font_ops.fonttools, scripts.font_ops.glyph_transform, scripts.font_ops.glyphs, scripts.font_ops.merge, scripts.font_ops.metadata, scripts.font_ops.metrics, scripts.font_ops.names, scripts.font_ops.nerd_font, scripts.font_ops.opentype, scripts.font_ops.subset, sys; assert 'glyphsLib' not in sys.modules; assert not any(name.startswith(('scripts.cjk', 'scripts.config', 'scripts.resolver')) for name in sys.modules)",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


class FontMergeOwnershipTest(unittest.TestCase):
    def test_success_closes_extra_font_and_transfers_base_font(self) -> None:
        base_font = MagicMock()
        extra_font = MagicMock()
        base_font.getGlyphOrder.return_value = [".notdef"]
        extra_font.getGlyphOrder.return_value = [".notdef"]

        with patch(
            "scripts.font_ops.merge.load_font",
            side_effect=(base_font, extra_font),
        ):
            result = merge_ttfonts("base.ttf", "extra.ttf")

        self.assertIs(result, base_font)
        base_font.close.assert_not_called()
        extra_font.close.assert_called_once_with()

    def test_failure_closes_base_font(self) -> None:
        base_font = MagicMock()

        with (
            patch(
                "scripts.font_ops.merge.load_font",
                side_effect=(base_font, RuntimeError("open failed")),
            ),
            self.assertRaisesRegex(RuntimeError, "open failed"),
        ):
            merge_ttfonts("base.ttf", "extra.ttf")

        base_font.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

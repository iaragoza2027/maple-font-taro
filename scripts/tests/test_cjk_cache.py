from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from scripts.cjk.cache import has_valid_cjk_variable_cache
from scripts.cjk.config import CJKBuildConfig, CJKOutputConfig, CJKSourceConfig


def write_test_font(path: Path) -> None:
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef"])
    builder.setupCharacterMap({})
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph()})
    builder.setupHorizontalMetrics({".notdef": (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "familyName": "Test",
            "styleName": "Regular",
            "uniqueFontIdentifier": "Test Regular",
            "fullName": "Test Regular",
            "psName": "Test-Regular",
        }
    )
    builder.setupOS2()
    builder.setupPost()
    builder.setupMaxp()
    path.parent.mkdir(parents=True, exist_ok=True)
    builder.save(path)


class CJKVariableCacheTest(unittest.TestCase):
    def make_config(self, root: Path) -> CJKBuildConfig:
        source_path = root / "source.ttf"
        source_path.write_bytes(b"source")
        return CJKBuildConfig(
            source=CJKSourceConfig(
                path=source_path,
                masters={
                    100: {"wght": 100},
                    400: {"wght": 400},
                    800: {"wght": 800},
                },
            ),
            output=CJKOutputConfig(dir=root / "output"),
        )

    def write_outputs(self, config: CJKBuildConfig) -> None:
        write_test_font(config.output.dir / config.output.regular_variable)
        write_test_font(config.output.dir / config.output.italic_variable)

    def test_cache_accepts_readable_outputs_after_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            self.write_outputs(config)

            self.assertTrue(has_valid_cjk_variable_cache(config))

            config.source.path.write_bytes(b"changed")
            self.assertTrue(has_valid_cjk_variable_cache(config))

    def test_missing_corrupt_and_zero_byte_outputs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))

            self.assertFalse(has_valid_cjk_variable_cache(config))

            regular_path = config.output.dir / config.output.regular_variable
            italic_path = config.output.dir / config.output.italic_variable
            self.write_outputs(config)
            italic_path.unlink()
            self.assertFalse(has_valid_cjk_variable_cache(config))

            self.write_outputs(config)
            regular_path.write_bytes(b"{")
            self.assertFalse(has_valid_cjk_variable_cache(config))

            self.write_outputs(config)
            regular_path.write_bytes(b"")
            self.assertFalse(has_valid_cjk_variable_cache(config))


if __name__ == "__main__":
    unittest.main()

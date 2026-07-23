from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from scripts.cjk.cache import (
    cjk_variable_manifest_path,
    has_valid_cjk_variable_cache,
    write_cjk_variable_manifest,
)
from scripts.cjk.config import CJKBuildConfig, CJKOutputConfig, CJKSourceConfig
from scripts.config.resolver import BuildConfigResolver


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

    def test_manifest_accepts_only_matching_readable_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            font_config = BuildConfigResolver().load_defaults()
            self.write_outputs(config)
            write_cjk_variable_manifest(config, font_config)

            self.assertTrue(has_valid_cjk_variable_cache(config, font_config))

            config.source.path.write_bytes(b"changed")
            self.assertFalse(has_valid_cjk_variable_cache(config, font_config))

    def test_missing_corrupt_and_zero_byte_artifacts_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            font_config = BuildConfigResolver().load_defaults()
            self.write_outputs(config)

            self.assertFalse(has_valid_cjk_variable_cache(config, font_config))
            cjk_variable_manifest_path(config).write_text("{", encoding="utf-8")
            self.assertFalse(has_valid_cjk_variable_cache(config, font_config))

            write_cjk_variable_manifest(config, font_config)
            regular_path = config.output.dir / config.output.regular_variable
            regular_path.write_bytes(b"")
            self.assertFalse(has_valid_cjk_variable_cache(config, font_config))

            self.write_outputs(config)
            manifest_path = cjk_variable_manifest_path(config)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["schema"] = 0
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertFalse(has_valid_cjk_variable_cache(config, font_config))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from scripts.cjk.cache import has_valid_cjk_static_cache, write_static_hash
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


class CJKStaticCacheTest(unittest.TestCase):
    def make_config(self, root: Path) -> CJKBuildConfig:
        return CJKBuildConfig(
            source=CJKSourceConfig(
                path=root / "source.ttf",
                masters={
                    100: {"wght": 100},
                    400: {"wght": 400},
                    800: {"wght": 800},
                },
            ),
            output=CJKOutputConfig(
                dir=root / "output",
                static_hash="static-cn.sha256",
            ),
        )

    def write_static(self, config: CJKBuildConfig) -> Path:
        static_dir = config.output.dir / config.output.static_dir
        write_test_font(static_dir / "MapleMonoCJK-Regular.ttf")
        write_static_hash(config, static_dir)
        return static_dir

    def test_directory_hash_validates_static_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            static_dir = self.write_static(config)

            self.assertTrue(has_valid_cjk_static_cache(config, static_dir, {"Regular"}))

            (static_dir / "MapleMonoCJK-Regular.ttf").write_bytes(b"changed")
            self.assertFalse(
                has_valid_cjk_static_cache(config, static_dir, {"Regular"})
            )

    def test_missing_hash_or_style_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            static_dir = self.write_static(config)
            config.output.dir.joinpath(config.output.static_hash).unlink()
            self.assertFalse(
                has_valid_cjk_static_cache(config, static_dir, {"Regular"})
            )

            write_static_hash(config, static_dir)
            self.assertFalse(has_valid_cjk_static_cache(config, static_dir, {"Bold"}))

    def test_variable_files_are_not_verified_by_cjk_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            regular = config.output.dir / config.output.regular_variable
            italic = config.output.dir / config.output.italic_variable
            regular.parent.mkdir(parents=True)
            regular.write_bytes(b"not inspected")
            italic.write_bytes(b"not inspected")

            self.assertFalse(
                has_valid_cjk_static_cache(
                    config,
                    config.output.dir / config.output.static_dir,
                    {"Regular"},
                )
            )


if __name__ == "__main__":
    unittest.main()

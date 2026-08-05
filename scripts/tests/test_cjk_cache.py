from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from scripts.cjk.cache import (
    has_valid_cjk_static_cache,
    verify_static_archive,
    write_static_hash,
)
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

    def write_archive(self, static_dir: Path, archive_path: Path) -> None:
        with ZipFile(archive_path, "w") as archive:
            for font_path in static_dir.glob("*.ttf"):
                archive.write(font_path, font_path.name)

    def test_static_archive_matches_committed_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            static_dir = self.write_static(config)
            archive_path = Path(tmp) / "cn-base-static.zip"
            self.write_archive(static_dir, archive_path)

            verify_static_archive(
                archive_path, config.output.dir / config.output.static_hash
            )

    def test_static_archive_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            self.write_static(config)
            archive_path = Path(tmp) / "cn-base-static.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("MapleMonoCJK-Regular.ttf", b"changed")

            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_static_archive(
                    archive_path, config.output.dir / config.output.static_hash
                )

    def test_static_archive_rejects_duplicate_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            static_dir = self.write_static(config)
            archive_path = Path(tmp) / "duplicate.zip"
            font_data = (static_dir / "MapleMonoCJK-Regular.ttf").read_bytes()
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("MapleMonoCJK-Regular.ttf", font_data)
                archive.writestr("MapleMonoCJK-Regular.ttf", font_data)

            with self.assertRaisesRegex(ValueError, "duplicate members"):
                verify_static_archive(
                    archive_path, config.output.dir / config.output.static_hash
                )

    def test_static_archive_rejects_invalid_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            self.write_static(config)
            archive_path = Path(tmp) / "invalid.zip"
            for member_name in (
                "nested/font.ttf",
                "README.md",
                "../font.ttf",
                r"..\font.ttf",
            ):
                with self.subTest(member_name=member_name):
                    with ZipFile(archive_path, "w") as archive:
                        archive.writestr(member_name, b"font")

                    with self.assertRaisesRegex(ValueError, "root-level TTF"):
                        verify_static_archive(
                            archive_path, config.output.dir / config.output.static_hash
                        )

    def test_static_archive_rejects_corrupt_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            self.write_static(config)
            archive_path = Path(tmp) / "corrupt.zip"
            archive_path.write_bytes(b"not a zip")

            with self.assertRaisesRegex(ValueError, "Invalid static archive"):
                verify_static_archive(
                    archive_path, config.output.dir / config.output.static_hash
                )

    def test_static_archive_rejects_empty_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            self.write_static(config)
            archive_path = Path(tmp) / "empty.zip"
            with ZipFile(archive_path, "w"):
                pass

            with self.assertRaisesRegex(ValueError, "empty"):
                verify_static_archive(
                    archive_path, config.output.dir / config.output.static_hash
                )

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

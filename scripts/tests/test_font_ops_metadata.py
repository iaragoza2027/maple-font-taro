from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from scripts.cjk.static import apply_cjk_meta_table
from scripts.font_ops.fonttools import MetaTable, load_font
from scripts.font_ops.metadata import set_meta_table
from scripts.task import googlefonts
from scripts.task.googlefonts import (
    DESIGN_LANGUAGES,
    SUPPORTED_LANGUAGES,
    apply_googlefonts_meta,
)
from scripts.tests.cjk_font_fixtures import build_test_font


class FontMetadataTest(unittest.TestCase):
    def test_set_meta_table_replaces_script_language_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font = build_test_font(Path(tmp) / "Fixture.ttf")
            try:
                set_meta_table(font, "Old", "Old")
                set_meta_table(font, "Latn", "Latn, Cyrl, Grek")

                meta = cast("MetaTable", font["meta"])
                self.assertEqual(
                    meta.data,
                    {"dlng": "Latn", "slng": "Latn, Cyrl, Grek"},
                )
            finally:
                font.close()

    def test_cjk_meta_table_keeps_code_page_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font = build_test_font(Path(tmp) / "Fixture.ttf")
            try:
                apply_cjk_meta_table(font, "Latn, Hans", 1 << 18)

                self.assertEqual(font.table("OS/2").ulCodePageRange1, 1 << 18)
                self.assertEqual(
                    cast("MetaTable", font["meta"]).data,
                    {"dlng": "Latn, Hans", "slng": "Latn, Hans"},
                )
            finally:
                font.close()

    def test_googlefonts_meta_updates_googlefonts_outputs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ttf_path = root / "MapleMono-Regular.ttf"
            static_path = root / "MapleMono-Bold.ttf"
            woff2_path = root / "MapleMono[wght].woff2"
            debug_path = root / "MapleMonoDebug-Regular.ttf"
            self._write_font(ttf_path, "Maple Mono", meta=("Old", "Old"))
            self._write_font(static_path, "Maple Mono Bold")
            self._write_font(woff2_path, "Maple Mono", flavor="woff2")
            self._write_font(debug_path, "Maple Mono Debug")
            debug_bytes = debug_path.read_bytes()

            updated = apply_googlefonts_meta((root,))

            self.assertCountEqual(updated, (ttf_path, static_path, woff2_path))
            self._assert_meta_table(ttf_path)
            self._assert_meta_table(static_path)
            self._assert_meta_table(woff2_path)
            self.assertEqual(debug_path.read_bytes(), debug_bytes)

    def test_googlefonts_run_applies_meta_after_successful_build(self) -> None:
        with (
            patch.object(googlefonts, "run_gftools_builder") as build,
            patch.object(googlefonts, "apply_googlefonts_meta") as apply_meta,
        ):
            googlefonts.run(Namespace(rebuild=False, qa=False))

        build.assert_called_once_with()
        apply_meta.assert_called_once_with()

    def _write_font(
        self,
        path: Path,
        family_name: str,
        *,
        flavor: str | None = None,
        meta: tuple[str, str] | None = None,
    ) -> None:
        source_path = path.with_suffix(".source.ttf")
        font = build_test_font(source_path)
        name_table = cast("Any", font["name"])
        for record in list(name_table.names):
            if record.nameID == 1:
                name_table.setName(
                    family_name,
                    record.nameID,
                    record.platformID,
                    record.platEncID,
                    record.langID,
                )
        if meta is not None:
            set_meta_table(font, *meta)
        if flavor is not None:
            font.flavor = flavor
        try:
            font.save(path)
        finally:
            font.close()

    def _assert_meta_table(self, path: Path) -> None:
        font = load_font(path)
        try:
            self.assertEqual(
                cast("MetaTable", font["meta"]).data,
                {
                    "dlng": DESIGN_LANGUAGES,
                    "slng": SUPPORTED_LANGUAGES,
                },
            )
        finally:
            font.close()


if __name__ == "__main__":
    unittest.main()

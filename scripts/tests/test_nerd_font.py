from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.font_ops.nerd_font import NerdFontVariant, parse_codes_from_json


class NerdFontHelpersTest(unittest.TestCase):
    def test_variant_preserves_nf_output_names(self) -> None:
        self.assertEqual(NerdFontVariant.from_options().symbol, "NF")
        self.assertEqual(NerdFontVariant.from_options(mono=True).suffix, "Mono")
        self.assertEqual(NerdFontVariant.from_options(mono=True).symbol, "NFo")
        self.assertEqual(NerdFontVariant.from_options(propo=True).symbol, "NFr")

    def test_variant_resolves_font_patcher_flags(self) -> None:
        variant = NerdFontVariant.from_options(extra_args=("--mono",))
        self.assertEqual(variant.suffix, "Mono")
        with self.assertRaises(ValueError):
            NerdFontVariant.from_options(mono=True, propo=True, reject_conflict=True)

    def test_variant_builds_shared_paths(self) -> None:
        variant = NerdFontVariant.from_options(mono=True)
        self.assertEqual(
            variant.base_path("source"),
            Path("source/MapleMono-NF-Base-Mono.ttf"),
        )
        self.assertEqual(
            variant.patched_style_path("fonts", "MapleMono", "Italic"),
            Path("fonts/MapleMono-NFo-Italic.ttf"),
        )
        self.assertEqual(
            variant.patched_font_path("fonts", "MapleMono-Regular.ttf"),
            Path("fonts/MapleMonoNerdFontMono-Regular.ttf"),
        )

    def test_parse_codes_from_json_loads_and_sorts_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "glyphnames.json"
            path.write_text(
                json.dumps(
                    {
                        "z": {"code": "e001"},
                        "a": {"code": "f0001"},
                        "duplicate": {"code": "e001"},
                        "metadata": {"name": "ignored"},
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(parse_codes_from_json(path), [0xE001, 0xF0001])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.config.resolver import BuildConfigResolver
from scripts.config.runtime import BuildRuntimeContext
from scripts.font_ops.nerd_font import NerdFontVariant, parse_codes_from_json


class NerdFontHelpersTest(unittest.TestCase):
    def test_variant_preserves_nf_output_names(self) -> None:
        self.assertEqual(NerdFontVariant.from_options().symbol, "NF")
        self.assertEqual(NerdFontVariant.from_options(mono=True).suffix, "Mono")
        self.assertEqual(NerdFontVariant.from_options(mono=True).symbol, "NFM")
        self.assertEqual(
            NerdFontVariant.from_options(mono=True).directory_name, "NFMono"
        )
        self.assertEqual(
            NerdFontVariant.from_options(mono=True).cjk_directory_name("CN"),
            "NFMono-CN",
        )
        self.assertEqual(NerdFontVariant.from_options(propo=True).symbol, "NFP")
        self.assertEqual(
            NerdFontVariant.from_options(propo=True).directory_name, "NFPropo"
        )
        self.assertEqual(
            NerdFontVariant.from_options(mono=True, propo=True).suffix,
            "Propo",
        )

    def test_variant_resolves_font_patcher_flags(self) -> None:
        variant = NerdFontVariant.from_options(extra_args=("--mono",))
        self.assertEqual(variant.suffix, "Mono")
        with self.assertRaises(ValueError):
            NerdFontVariant.from_options(mono=True, propo=True, reject_conflict=True)

    def test_variant_builds_shared_paths(self) -> None:
        variant = NerdFontVariant.from_options(mono=True)
        self.assertEqual(
            variant.base_path("sources"),
            Path("sources/MapleMono-NF-Base-Mono.ttf"),
        )
        self.assertEqual(
            variant.patched_style_path("fonts", "MapleMono", "Italic"),
            Path("fonts/MapleMono-NFM-Italic.ttf"),
        )
        self.assertEqual(
            variant.patched_font_path("fonts", "MapleMono-Regular.ttf"),
            Path("fonts/MapleMonoNerdFontMono-Regular.ttf"),
        )

    def test_runtime_context_uses_variant_directories(self) -> None:
        config = BuildConfigResolver().load_defaults()
        for flags, directory in (
            ({}, "NF"),
            ({"mono": True}, "NFMono"),
            ({"propo": True}, "NFPropo"),
        ):
            with self.subTest(directory=directory):
                config.nerd_font.mono = flags.get("mono", False)
                config.nerd_font.propo = flags.get("propo", False)
                runtime_context = BuildRuntimeContext.from_config(config)
                self.assertEqual(
                    runtime_context.output_nf, str(Path("fonts") / directory)
                )
                self.assertEqual(
                    runtime_context.output_nf_variable,
                    str(Path("fonts") / f"Variable-{directory}"),
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

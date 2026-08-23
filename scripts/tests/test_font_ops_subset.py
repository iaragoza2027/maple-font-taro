from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fontTools.subset import Options

from scripts.font_ops.subset import SubsetConfig, subset_to_codepoints


class SubsetFontOpsTest(unittest.TestCase):
    def test_subset_requires_exactly_one_target(self) -> None:
        with self.assertRaises(ValueError):
            from scripts.font_ops.subset import _subset

            _subset(MagicMock(), options=None)

    def test_subset_config_applies_explicit_values(self) -> None:
        config = SubsetConfig(
            hinting=False,
            layout_features=(),
            name_ids=("*",),
            name_legacy=True,
            name_languages=("*",),
            notdef_outline=True,
            recalc_bounds=True,
            recalc_timestamp=False,
            recommended_glyphs=False,
        )

        with patch("scripts.font_ops.subset.Subsetter") as subsetter:
            subset_to_codepoints(MagicMock(), {65}, options=config)

        options = subsetter.call_args.kwargs["options"]
        self.assertFalse(options.hinting)
        self.assertEqual(options.layout_features, [])
        self.assertEqual(options.name_IDs, ["*"])
        self.assertTrue(options.name_legacy)
        self.assertEqual(options.name_languages, ["*"])
        self.assertTrue(options.notdef_outline)
        self.assertTrue(options.recalc_bounds)
        self.assertFalse(options.recalc_timestamp)
        self.assertFalse(options.recommended_glyphs)

    def test_subset_config_preserves_unspecified_fonttools_defaults(self) -> None:
        with patch("scripts.font_ops.subset.Subsetter") as subsetter:
            subset_to_codepoints(MagicMock(), {65}, options=SubsetConfig(hinting=False))

        options = subsetter.call_args.kwargs["options"]
        defaults = Options()
        self.assertFalse(options.hinting)
        self.assertEqual(options.layout_features, defaults.layout_features)
        self.assertEqual(options.name_IDs, defaults.name_IDs)
        self.assertEqual(options.notdef_outline, defaults.notdef_outline)


if __name__ == "__main__":
    unittest.main()

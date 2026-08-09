from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from scripts.font_ops.subset import subset_to_codepoints, subset_to_glyphs


class SubsetFontOpsTest(unittest.TestCase):
    def test_subset_to_codepoints_reuses_configured_options(self) -> None:
        font = MagicMock()
        options = MagicMock()
        subsetter = MagicMock()

        with patch(
            "scripts.font_ops.subset.Subsetter", return_value=subsetter
        ) as factory:
            result = subset_to_codepoints(font, (0x41, 0x42), options=options)

        self.assertIs(result, font)
        factory.assert_called_once_with(options=options)
        subsetter.populate.assert_called_once_with(unicodes=(0x41, 0x42))
        subsetter.subset.assert_called_once_with(font)

    def test_subset_to_glyphs_uses_default_options(self) -> None:
        font = MagicMock()
        subsetter = MagicMock()

        with patch(
            "scripts.font_ops.subset.Subsetter", return_value=subsetter
        ) as factory:
            result = subset_to_glyphs(font, [".notdef", "A"])

        self.assertIs(result, font)
        factory.assert_called_once_with()
        subsetter.populate.assert_called_once_with(glyphs=[".notdef", "A"])
        subsetter.subset.assert_called_once_with(font)

    def test_subset_requires_exactly_one_target(self) -> None:
        with self.assertRaises(ValueError):
            from scripts.font_ops.subset import _subset

            _subset(MagicMock(), options=None)


if __name__ == "__main__":
    unittest.main()

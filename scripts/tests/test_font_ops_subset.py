from __future__ import annotations

import unittest
from unittest.mock import MagicMock


class SubsetFontOpsTest(unittest.TestCase):
    def test_subset_requires_exactly_one_target(self) -> None:
        with self.assertRaises(ValueError):
            from scripts.font_ops.subset import _subset

            _subset(MagicMock(), options=None)


if __name__ == "__main__":
    unittest.main()

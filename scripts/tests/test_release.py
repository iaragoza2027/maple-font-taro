from __future__ import annotations

import unittest

from scripts.task.release import next_version


class ReleaseVersionTest(unittest.TestCase):
    def test_minor_version_is_calculated_without_mutation(self) -> None:
        self.assertEqual(next_version("7.9", "minor"), "7.10")

    def test_major_version_resets_minor(self) -> None:
        self.assertEqual(next_version("7.9", "major"), "8.0")

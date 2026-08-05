from __future__ import annotations

import unittest

from scripts.utils.version import (
    font_version_for_core,
    parse_project_version,
    parse_version_tag,
    project_version_from_font_version,
    version_tag,
)


class VersionParsingTest(unittest.TestCase):
    def test_beta_project_version_maps_to_dotted_beta_tag(self) -> None:
        parsed = parse_project_version("8.0b1")

        self.assertEqual(parsed.core, "8.0")
        self.assertEqual(parsed.tag, "8.0-beta.1")
        self.assertEqual(version_tag("8.0b1"), "v8.0-beta.1")

    def test_stable_project_version_maps_to_stable_tag(self) -> None:
        self.assertEqual(version_tag("7.9"), "v7.9")

    def test_tag_parser_accepts_new_and_legacy_beta_syntax(self) -> None:
        self.assertEqual(parse_version_tag("v8.0-beta.1").project, "8.0b1")
        self.assertEqual(parse_version_tag("v8.0-beta36").project, "8.0b36")

    def test_font_version_preserves_the_core_minor_slot(self) -> None:
        self.assertEqual(font_version_for_core("7.9"), "7.900")
        self.assertEqual(font_version_for_core("8.0"), "8.000")
        self.assertEqual(font_version_for_core("8.1"), "8.100")

    def test_font_version_fallback_recovers_the_core_version(self) -> None:
        self.assertEqual(project_version_from_font_version("7.900"), "7.9")
        self.assertEqual(project_version_from_font_version("8.001"), "8.0")


if __name__ == "__main__":
    unittest.main()

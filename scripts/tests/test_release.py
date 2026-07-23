from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from scripts.task.release import next_version, release


class ReleaseVersionTest(unittest.TestCase):
    def test_minor_version_is_calculated_without_mutation(self) -> None:
        self.assertEqual(next_version("7.9", "minor"), "7.10")

    def test_major_version_resets_minor(self) -> None:
        self.assertEqual(next_version("7.9", "major"), "8.0")

    def test_dry_run_only_prints_the_release_plan(self) -> None:
        output = StringIO()
        with (
            patch("scripts.task.release.project_version", return_value="7.9"),
            patch("scripts.task.release.input") as prompt,
            patch("scripts.task.release.generate_release_assets") as generate,
            patch("scripts.task.release.publish_release") as publish,
            patch("scripts.task.release.run_command") as run,
            redirect_stdout(output),
        ):
            release("minor", dry=True)

        self.assertIn("Tag: v7.10", output.getvalue())
        self.assertIn("Build: build.py --ttf-only", output.getvalue())
        prompt.assert_not_called()
        generate.assert_not_called()
        publish.assert_not_called()
        run.assert_not_called()

from __future__ import annotations

import subprocess
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import call, patch

from scripts.task.publish import publish, resolve_release_tags


class ResolveReleaseTagsTest(unittest.TestCase):
    @patch("scripts.task.publish.get_output")
    def test_explicit_tag_is_used_and_previous_tag_comes_from_ancestry(
        self, get_output
    ) -> None:
        get_output.side_effect = ["commit-id", "v7.8"]

        self.assertEqual(resolve_release_tags("v7.9"), ("v7.8", "v7.9"))

        self.assertEqual(
            get_output.call_args_list,
            [
                call(["git", "rev-parse", "--verify", "refs/tags/v7.9"]),
                call(["git", "describe", "--tags", "--abbrev=0", "v7.9^"]),
            ],
        )

    @patch("scripts.task.publish.get_output")
    def test_unique_tag_pointing_at_head_is_used(self, get_output) -> None:
        get_output.side_effect = ["v7.9", "v7.8"]

        self.assertEqual(resolve_release_tags(None), ("v7.8", "v7.9"))

        self.assertEqual(
            get_output.call_args_list,
            [
                call(["git", "tag", "--points-at", "HEAD"]),
                call(["git", "describe", "--tags", "--abbrev=0", "v7.9^"]),
            ],
        )

    @patch("scripts.task.publish.get_output", return_value="")
    def test_no_tag_at_head_requires_explicit_tag(self, get_output) -> None:
        with self.assertRaisesRegex(ValueError, "No release tag points at HEAD"):
            resolve_release_tags(None)

        get_output.assert_called_once_with(["git", "tag", "--points-at", "HEAD"])

    @patch("scripts.task.publish.get_output", return_value="v7.9\nv7.9-hotfix")
    def test_multiple_tags_at_head_require_explicit_tag(self, get_output) -> None:
        with self.assertRaisesRegex(ValueError, "Multiple release tags point at HEAD"):
            resolve_release_tags(None)

        get_output.assert_called_once_with(["git", "tag", "--points-at", "HEAD"])

    @patch("scripts.task.publish.get_output")
    def test_unknown_explicit_tag_fails_before_ancestry_lookup(
        self, get_output
    ) -> None:
        get_output.side_effect = subprocess.CalledProcessError(1, ["git"])

        with self.assertRaisesRegex(ValueError, "Unknown release tag: v7.9"):
            resolve_release_tags("v7.9")

        get_output.assert_called_once_with(
            ["git", "rev-parse", "--verify", "refs/tags/v7.9"]
        )

    @patch("scripts.task.publish.get_output")
    def test_tag_without_previous_ancestor_fails(self, get_output) -> None:
        ancestry_error = subprocess.CalledProcessError(128, ["git"])
        get_output.side_effect = ["commit-id", ancestry_error]

        with self.assertRaises(subprocess.CalledProcessError):
            resolve_release_tags("v1.0")

        self.assertEqual(
            get_output.call_args_list,
            [
                call(["git", "rev-parse", "--verify", "refs/tags/v1.0"]),
                call(["git", "describe", "--tags", "--abbrev=0", "v1.0^"]),
            ],
        )


class PublishTest(unittest.TestCase):
    @patch("scripts.task.publish.subprocess.run")
    @patch(
        "scripts.task.publish.Path.read_text",
        return_value="<!-- changelog -->\nhttps://<url>",
    )
    @patch("scripts.task.publish.get_output")
    def test_dry_run_uses_resolved_explicit_tag(
        self, get_output, read_text, run
    ) -> None:
        get_output.side_effect = ["commit-id", "v7.8", "Change summary"]
        output = StringIO()

        with redirect_stdout(output):
            publish(write=False, tag="v7.9", dry=True)

        self.assertIn("changelog:\nChange summary", output.getvalue())
        self.assertIn("gh release create v7.9", output.getvalue())
        self.assertEqual(
            get_output.call_args_list,
            [
                call(["git", "rev-parse", "--verify", "refs/tags/v7.9"]),
                call(["git", "describe", "--tags", "--abbrev=0", "v7.9^"]),
                call(
                    [
                        "git",
                        "log",
                        "--pretty=format:- %s\n%b",
                        "v7.8..v7.9",
                    ]
                ),
            ],
        )
        read_text.assert_called_once_with()
        run.assert_not_called()

    @patch("scripts.task.publish.subprocess.run")
    @patch("scripts.task.publish.Path.write_text")
    @patch(
        "scripts.task.publish.Path.read_text",
        return_value="<!-- changelog -->\nhttps://<url>",
    )
    @patch("scripts.task.publish.get_output")
    def test_publish_command_uses_resolved_target_tag(
        self, get_output, read_text, write_text, run
    ) -> None:
        get_output.side_effect = ["commit-id", "v7.8", "Change summary"]

        publish(write=False, tag="v7.9", dry=False)

        run.assert_called_once_with(
            [
                "gh",
                "release",
                "create",
                "v7.9",
                "release/**/*.*",
                "--notes-file",
                ".github/release_template.md",
                "-t",
                "V7.9",
                "--draft",
            ],
            check=True,
        )
        read_text.assert_called_once_with()
        write_text.assert_called_once()

    @patch("scripts.task.publish.subprocess.run")
    @patch("scripts.task.publish.get_output")
    def test_unknown_tag_does_not_publish(self, get_output, run) -> None:
        get_output.side_effect = subprocess.CalledProcessError(1, ["git"])

        with self.assertRaisesRegex(ValueError, "Unknown release tag: v7.9"):
            publish(write=False, tag="v7.9", dry=False)

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

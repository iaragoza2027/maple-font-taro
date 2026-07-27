from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from scripts.task.release import (
    ReleasePlan,
    generate_release_assets,
    next_version,
    release,
)


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


class ReleaseAssetTest(unittest.TestCase):
    def test_variable_woff2_output_is_recreated_from_a_clean_directory(self) -> None:
        for starts_with_output in (False, True):
            with (
                self.subTest(starts_with_output=starts_with_output),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                (root / "fonts" / "CN").mkdir(parents=True)
                variable_output = root / "woff2" / "var"
                if starts_with_output:
                    variable_output.mkdir(parents=True)
                    (variable_output / "stale.woff2").write_bytes(b"stale")

                plan = ReleasePlan(
                    tag="v0.0",
                    build_args=(),
                    fontsource_dir="cdn/fontsource",
                    variable_woff2_dir="woff2/var",
                )

                def convert(_input_path, output_dir, **_kwargs):
                    output = Path(output_dir)
                    output.mkdir(parents=True, exist_ok=True)
                    generated = output / "generated.woff2"
                    generated.write_bytes(b"generated")
                    return [generated]

                previous_cwd = Path.cwd()
                try:
                    os.chdir(root)
                    with (
                        patch("scripts.task.release.build_main"),
                        patch(
                            "scripts.task.release.convert_to_web",
                            side_effect=convert,
                        ),
                        patch("scripts.task.release.rename_woff_files"),
                        patch("scripts.task.release.run_command"),
                    ):
                        generate_release_assets(plan)
                finally:
                    os.chdir(previous_cwd)

                self.assertEqual(
                    [path.name for path in variable_output.iterdir()],
                    ["generated.woff2"],
                )

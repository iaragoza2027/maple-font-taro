from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import call, patch

from scripts.task.release import (
    ReleaseBump,
    ReleasePlan,
    generate_release_assets,
    next_font_version,
    next_version,
    release,
    select_release_bump,
)


class ReleaseVersionTest(unittest.TestCase):
    def test_minor_version_is_calculated_without_mutation(self) -> None:
        self.assertEqual(next_version("7.9", "minor"), "7.10")

    def test_major_version_resets_minor(self) -> None:
        self.assertEqual(next_version("7.9", "major"), "8.0")

    def test_pre_major_starts_and_increments_beta_versions(self) -> None:
        self.assertEqual(next_version("7.9", "pre-major"), "8.0b1")
        self.assertEqual(next_version("8.0b1", "pre-major"), "8.0b2")

    def test_matching_bump_finalizes_a_beta_release_line(self) -> None:
        self.assertEqual(next_version("8.0b2", "major"), "8.0")
        self.assertEqual(next_version("7.10b2", "minor"), "7.10")

    def test_font_version_uses_a_single_release_line_sequence(self) -> None:
        self.assertEqual(next_font_version("7.9", "7.900", "8.0b1"), "8.001")
        self.assertEqual(next_font_version("8.0b1", "8.001", "8.0b2"), "8.002")
        self.assertEqual(next_font_version("8.0b2", "8.002", "8.0"), "8.003")

    def test_dry_run_only_prints_the_release_plan(self) -> None:
        output = StringIO()
        with (
            patch("scripts.task.release.project_version", return_value="7.9"),
            patch("scripts.task.release.read_font_version", return_value="7.900"),
            patch("scripts.task.release.input") as prompt,
            patch("scripts.task.release.generate_release_assets") as generate,
            patch("scripts.task.release.publish_release") as publish,
            patch("scripts.task.release.run_command") as run,
            redirect_stdout(output),
        ):
            release("minor", dry=True)

        self.assertIn("Tag: v7.10", output.getvalue())
        self.assertIn("Font version: 7.100", output.getvalue())
        self.assertIn("Build: build.py --ttf-only", output.getvalue())
        prompt.assert_not_called()
        generate.assert_not_called()
        publish.assert_not_called()
        run.assert_not_called()

    @patch("questionary.select")
    def test_release_menu_shows_all_target_versions_and_defaults_to_minor(
        self, select
    ) -> None:
        plans: dict[ReleaseBump, ReleasePlan] = {
            bump: ReleasePlan(
                tag=tag,
                build_args=(),
                project_version=project,
                font_version=font,
            )
            for bump, tag, project, font in (
                ("minor", "v7.10", "7.10", "7.100"),
                ("major", "v8.0", "8.0", "8.000"),
                ("pre-minor", "v7.10-beta.1", "7.10b1", "7.101"),
                ("pre-major", "v8.0-beta.1", "8.0b1", "8.001"),
            )
        }
        select.return_value.ask.return_value = "pre-major"

        selected = select_release_bump(plans)

        self.assertEqual(selected, "pre-major")
        choices = select.call_args.kwargs["choices"]
        self.assertEqual(
            [choice.value for choice in choices],
            ["minor", "major", "pre-minor", "pre-major"],
        )
        self.assertEqual(
            [choice.title for choice in choices],
            [
                "minor       → v7.10            (font 7.100)",
                "major       → v8.0             (font 8.000)",
                "pre-minor   → v7.10-beta.1     (font 7.101)",
                "pre-major   → v8.0-beta.1      (font 8.001)",
            ],
        )
        self.assertEqual(select.call_args.kwargs["default"], "minor")

    @patch("scripts.task.release.publish_release")
    @patch("scripts.task.release.generate_release_assets")
    @patch("scripts.task.release.run_command")
    @patch("scripts.task.release.input", return_value="")
    @patch("scripts.task.release.select_release_bump", return_value=None)
    @patch("scripts.task.release.create_release_plans")
    def test_cancelled_menu_does_not_mutate_or_publish(
        self,
        create_plans,
        _select,
        prompt,
        run,
        generate,
        publish,
    ) -> None:
        create_plans.return_value = {}

        release(None, dry=False)

        prompt.assert_not_called()
        run.assert_not_called()
        generate.assert_not_called()
        publish.assert_not_called()

    def test_selected_menu_plan_is_reused_for_build_and_publish(self) -> None:
        plan = ReleasePlan(
            tag="v7.10",
            build_args=(),
            project_version="7.10",
            font_version="7.100",
        )
        with (
            patch(
                "scripts.task.release.create_release_plans",
                return_value={"minor": plan},
            ),
            patch("scripts.task.release.select_release_bump", return_value="minor"),
            patch("scripts.task.release.input", return_value=""),
            patch("scripts.task.release.run_command"),
            patch("scripts.task.release.update_font_version"),
            patch("scripts.task.release.generate_release_assets") as generate,
            patch("scripts.task.release.publish_release") as publish,
        ):
            release(None, dry=False)

        generate.assert_called_once_with(plan)
        publish.assert_called_once_with(plan)


class ReleaseAssetTest(unittest.TestCase):
    def test_variable_woff2_output_is_recreated_from_a_clean_directory(self) -> None:
        for starts_with_output in (False, True):
            with (
                self.subTest(starts_with_output=starts_with_output),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                (root / "fonts" / "CN").mkdir(parents=True)
                variable_output = root / "woff2" / "variable"
                if starts_with_output:
                    variable_output.mkdir(parents=True)
                    (variable_output / "stale.woff2").write_bytes(b"stale")

                plan = ReleasePlan(
                    tag="v0.0",
                    build_args=(),
                    fontsource_dir="cdn/fontsource",
                    variable_woff2_dir="woff2/variable",
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

    def test_variable_woff2_builds_default_narrow_and_slim_widths(self) -> None:
        plan = ReleasePlan(tag="v0.0", build_args=("--build",))
        with (  # noqa: SIM117
            patch("scripts.task.release.build_main") as build,
            patch("scripts.task.release.convert_to_web"),
            patch("scripts.task.release.rename_woff_files"),
            patch("scripts.task.release.run_command"),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "fonts" / "CN").mkdir(parents=True)
                previous_cwd = Path.cwd()
                try:
                    os.chdir(root)
                    generate_release_assets(plan)
                finally:
                    os.chdir(previous_cwd)

        self.assertEqual(
            build.call_args_list,
            [
                call(["--build"], "v0.0"),
                call(["--build", "--width", "narrow"], "v0.0"),
                call(["--build", "--width", "slim"], "v0.0"),
            ],
        )

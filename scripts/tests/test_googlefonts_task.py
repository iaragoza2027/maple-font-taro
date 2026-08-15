from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.task import googlefonts


class GoogleFontsTaskTest(unittest.TestCase):
    def parse_args(self, *arguments: str) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        googlefonts.register_parser(subparsers)
        return parser.parse_args(["googlefonts", *arguments])

    def test_parser_defaults_to_build_only(self) -> None:
        args = self.parse_args()

        self.assertFalse(args.rebuild)
        self.assertFalse(args.qa)

    def test_parser_accepts_rebuild_flag(self) -> None:
        args = self.parse_args("--rebuild")

        self.assertTrue(args.rebuild)

    def test_parser_accepts_qa_flag(self) -> None:
        args = self.parse_args("--qa")

        self.assertTrue(args.qa)

    def test_build_only_keeps_existing_variable_output_and_runs_builder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            variable_dir = Path(directory) / "variable"
            variable_dir.mkdir()
            stale_font = variable_dir / "stale.ttf"
            stale_font.write_bytes(b"stale")

            with (
                patch.object(googlefonts, "VARIABLE_OUTPUT_DIR", variable_dir),
                patch.object(googlefonts, "_regenerate_designspace") as regenerate,
                patch.object(googlefonts, "_run_gftools_builder") as run_builder,
                patch.object(googlefonts, "_run_fontbakery") as run_fontbakery,
            ):
                googlefonts.run(self.parse_args())

            self.assertTrue(stale_font.exists())
            regenerate.assert_not_called()
            run_builder.assert_called_once_with()
            run_fontbakery.assert_not_called()

    def test_rebuild_regenerates_designspace_before_builder(self) -> None:
        events: list[str] = []

        with (
            patch.object(
                googlefonts,
                "_regenerate_designspace",
                side_effect=lambda: events.append("designspace"),
            ) as regenerate,
            patch.object(
                googlefonts,
                "_run_gftools_builder",
                side_effect=lambda: events.append("builder"),
            ) as run_builder,
        ):
            googlefonts.run(self.parse_args("--rebuild"))

        regenerate.assert_called_once_with()
        run_builder.assert_called_once_with()
        self.assertEqual(events, ["designspace", "builder"])

    def test_qa_cleans_variable_output_before_running_builder_and_fontbakery(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            variable_dir = Path(directory) / "variable"
            variable_dir.mkdir()
            (variable_dir / "stale.ttf").write_bytes(b"stale")
            events: list[str] = []

            with (
                patch.object(googlefonts, "VARIABLE_OUTPUT_DIR", variable_dir),
                patch.object(googlefonts, "_regenerate_designspace") as regenerate,
                patch.object(
                    googlefonts,
                    "_run_gftools_builder",
                    side_effect=lambda: events.append("builder"),
                ) as run_builder,
                patch.object(
                    googlefonts,
                    "_run_fontbakery",
                    side_effect=lambda: events.append("fontbakery"),
                ) as run_fontbakery,
            ):
                googlefonts.run(self.parse_args("--qa"))

            self.assertFalse(variable_dir.exists())
            regenerate.assert_not_called()
            run_builder.assert_called_once_with()
            run_fontbakery.assert_called_once_with()
            self.assertEqual(events, ["builder", "fontbakery"])

    def test_qa_with_rebuild_regenerates_before_build_and_fontbakery(self) -> None:
        events: list[str] = []

        with (
            patch.object(
                googlefonts,
                "_regenerate_designspace",
                side_effect=lambda: events.append("designspace"),
            ) as regenerate,
            patch.object(
                googlefonts,
                "_run_gftools_builder",
                side_effect=lambda: events.append("builder"),
            ) as run_builder,
            patch.object(
                googlefonts,
                "_run_fontbakery",
                side_effect=lambda: events.append("fontbakery"),
            ) as run_fontbakery,
        ):
            googlefonts.run(self.parse_args("--rebuild", "--qa"))

        regenerate.assert_called_once_with()
        run_builder.assert_called_once_with()
        run_fontbakery.assert_called_once_with()
        self.assertEqual(events, ["designspace", "builder", "fontbakery"])

    def test_qa_does_not_run_fontbakery_when_builder_fails(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                googlefonts,
                "VARIABLE_OUTPUT_DIR",
                Path(directory) / "variable",
            ),
            patch.object(googlefonts, "_regenerate_designspace") as regenerate,
            patch.object(
                googlefonts,
                "_run_gftools_builder",
                side_effect=RuntimeError("builder failed"),
            ) as run_builder,
            patch.object(googlefonts, "_run_fontbakery") as run_fontbakery,
            self.assertRaisesRegex(RuntimeError, "builder failed"),
        ):
            googlefonts.run(self.parse_args("--qa"))

        regenerate.assert_not_called()
        run_builder.assert_called_once_with()
        run_fontbakery.assert_not_called()

    def test_designspace_failure_stops_build_and_qa(self) -> None:
        with (
            patch.object(
                googlefonts,
                "_regenerate_designspace",
                side_effect=RuntimeError("designspace failed"),
            ) as regenerate,
            patch.object(googlefonts, "_run_gftools_builder") as run_builder,
            patch.object(googlefonts, "_run_fontbakery") as run_fontbakery,
            self.assertRaisesRegex(RuntimeError, "designspace failed"),
        ):
            googlefonts.run(self.parse_args("--rebuild", "--qa"))

        regenerate.assert_called_once_with()
        run_builder.assert_not_called()
        run_fontbakery.assert_not_called()

    def test_fontbakery_uses_documented_argv_and_restores_process_argv(self) -> None:
        original_argv = sys.argv
        observed_argv: list[str] = []
        interpolatable_logger = logging.getLogger(
            googlefonts.INTERPOLATABLE_LOGGER_NAME
        )
        previous_log_level = interpolatable_logger.level
        observed_log_levels: list[int] = []

        def fake_main() -> int:
            observed_argv.extend(sys.argv)
            observed_log_levels.append(interpolatable_logger.level)
            return 0

        try:
            interpolatable_logger.setLevel(logging.INFO)
            with patch("fontbakery.cli.main", side_effect=fake_main):
                googlefonts._run_fontbakery()
        finally:
            interpolatable_logger.setLevel(previous_log_level)

        self.assertIs(sys.argv, original_argv)
        self.assertEqual(observed_argv, ["fontbakery", *googlefonts.FONTBAKERY_ARGS])
        self.assertEqual(observed_log_levels, [logging.WARNING])
        self.assertEqual(interpolatable_logger.level, previous_log_level)

    def test_gftools_uses_documented_config_and_restores_process_cwd(self) -> None:
        original_cwd = Path.cwd()
        observed: list[tuple[list[str], Path]] = []

        def fake_main(arguments: list[str]) -> None:
            observed.append((arguments, Path.cwd()))
            os.chdir(tempfile.gettempdir())
            raise SystemExit(0)

        with patch("gftools.builder.main", side_effect=fake_main):
            googlefonts._run_gftools_builder()

        self.assertEqual(Path.cwd(), original_cwd)
        self.assertEqual(observed, [([str(googlefonts.BUILDER_CONFIG)], original_cwd)])

    def test_designspace_uses_sources_as_input_and_output(self) -> None:
        with patch("scripts.task.designspace.generate_designspaces") as generate:
            googlefonts._regenerate_designspace()

        generate.assert_called_once_with(googlefonts.SOURCE_DIR, googlefonts.SOURCE_DIR)

    def test_gftools_failure_preserves_nonzero_exit_status(self) -> None:
        with (
            patch("gftools.builder.main", return_value=1),
            self.assertRaisesRegex(SystemExit, "1"),
        ):
            googlefonts._run_gftools_builder()

    def test_fontbakery_failure_preserves_nonzero_exit_status(self) -> None:
        with (
            patch("fontbakery.cli.main", return_value=1),
            self.assertRaisesRegex(SystemExit, "1"),
        ):
            googlefonts._run_fontbakery()


if __name__ == "__main__":
    unittest.main()

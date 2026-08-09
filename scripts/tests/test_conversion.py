from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.font_ops.conversion import (
    WebFontConversionJob,
    _convert_font_to_web,
    convert_to_web,
)


class WebFontConversionTest(unittest.TestCase):
    def test_converts_font_files_in_parallel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "TTF"
            target_dir = Path(tmp) / "Woff2"
            source_dir.mkdir()
            for name in ("MapleMono-Bold.ttf", "MapleMono-Regular.ttf"):
                (source_dir / name).write_bytes(b"")
            (source_dir / "README.txt").write_text("unrelated", encoding="utf-8")

            with (
                patch(
                    "scripts.font_ops.conversion.run_jobs",
                    side_effect=lambda _executor, worker, jobs: [
                        worker(job) for job in jobs
                    ],
                ),
                patch(
                    "scripts.font_ops.conversion.create_process_executor"
                ) as executor_type,
                patch(
                    "scripts.font_ops.conversion._convert_font_to_web",
                    side_effect=lambda job: (
                        job.target_dir
                        / (
                            f"{job.font_path.stem}.woff2"
                            if job.flavor == "woff2"
                            else f"{job.font_path.name}.{job.flavor}"
                        )
                    ),
                ),
            ):
                executor = MagicMock()
                executor.__enter__.return_value = executor
                executor_type.return_value = executor

                outputs = convert_to_web(source_dir, target_dir, "woff2")

            executor_type.assert_called_once_with(2, fallback_to_threads=True)
            self.assertEqual(
                outputs,
                [
                    target_dir / "MapleMono-Bold.woff2",
                    target_dir / "MapleMono-Regular.woff2",
                ],
            )

    def test_web_font_worker_saves_with_the_requested_flavor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "MapleMono-Regular.ttf"
            output_dir = Path(tmp) / "Woff2"
            source.write_bytes(b"")
            output_dir.mkdir()
            font = MagicMock()

            with (
                patch(
                    "scripts.font_ops.conversion.load_font",
                    return_value=font,
                ) as ttfont,
                patch("scripts.font_ops.conversion.logger.info") as log_info,
            ):
                result = _convert_font_to_web(
                    WebFontConversionJob(source, output_dir, "woff2")
                )

            target = output_dir / "MapleMono-Regular.woff2"
            ttfont.assert_called_once_with(source)
            self.assertEqual(font.flavor, "woff2")
            font.save.assert_called_once_with(target, reorderTables=False)
            font.close.assert_called_once()
            self.assertEqual(result, target)
            log_info.assert_called_once_with("Saved %s font to %s", "WOFF2", target)

    def test_uses_a_caller_owned_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "MapleMono-Regular.ttf"
            source.write_bytes(b"")
            executor = MagicMock()
            expected = [source.with_suffix(".woff2")]

            with patch(
                "scripts.font_ops.conversion.run_jobs", return_value=expected
            ) as run_jobs:
                outputs = convert_to_web(source, flavor="woff2", executor=executor)

            self.assertEqual(outputs, expected)
            self.assertIs(run_jobs.call_args.args[0], executor)

    def test_explicit_inputs_ignore_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "TTF"
            target_dir = Path(tmp) / "Woff2"
            source_dir.mkdir()
            current = source_dir / "MapleMono-Regular.ttf"
            stale = source_dir / "OldFamily-Regular.ttf"
            current.write_bytes(b"")
            stale.write_bytes(b"")
            executor = MagicMock()

            with patch(
                "scripts.font_ops.conversion.run_jobs",
                side_effect=lambda _executor, _worker, jobs: [
                    job.target_dir
                    / (
                        f"{job.font_path.stem}.woff2"
                        if job.flavor == "woff2"
                        else f"{job.font_path.name}.{job.flavor}"
                    )
                    for job in jobs
                ],
            ) as run_jobs:
                outputs = convert_to_web(
                    [current],
                    target_dir,
                    "woff2",
                    executor=executor,
                )

            self.assertEqual(outputs, [target_dir / "MapleMono-Regular.woff2"])
            self.assertEqual(
                [job.font_path for job in run_jobs.call_args.args[2]],
                [current],
            )
            self.assertTrue(stale.is_file())

    def test_explicit_inputs_fail_before_scheduling_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "MapleMono-Regular.ttf"
            executor = MagicMock()

            with (
                patch("scripts.font_ops.conversion.run_jobs") as run_jobs,
                self.assertRaisesRegex(
                    FileNotFoundError,
                    "Missing WOFF2 conversion input files",
                ),
            ):
                convert_to_web(
                    [source],
                    Path(tmp) / "Woff2",
                    executor=executor,
                )

            run_jobs.assert_not_called()

    def test_explicit_inputs_reject_duplicate_targets_before_scheduling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "current" / "MapleMono-Regular.ttf"
            second = Path(tmp) / "stale" / "MapleMono-Regular.ttf"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_bytes(b"")
            second.write_bytes(b"")
            executor = MagicMock()

            with (
                patch("scripts.font_ops.conversion.run_jobs") as run_jobs,
                self.assertRaisesRegex(
                    ValueError,
                    "Duplicate WOFF2 conversion output paths",
                ),
            ):
                convert_to_web(
                    [first, second],
                    Path(tmp) / "Woff2",
                    executor=executor,
                )

            run_jobs.assert_not_called()


if __name__ == "__main__":
    unittest.main()

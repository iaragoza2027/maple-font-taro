from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.font_ops.conversion import convert_to_web
from scripts.pipeline import Woff2BuildJob, build_woff2_font_job


class WebFontConversionTest(unittest.TestCase):
    def test_converts_font_files_in_parallel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "TTF"
            target_dir = Path(tmp) / "Woff2"
            source_dir.mkdir()
            for name in ("MapleMono-Bold.ttf", "MapleMono-Regular.ttf"):
                (source_dir / name).write_bytes(b"")

            def run_map(function, *iterables):
                return [function(*args) for args in zip(*iterables, strict=True)]

            with (
                patch(
                    "scripts.font_ops.conversion._convert_font_to_web",
                    side_effect=lambda source, target, flavor: (
                        target / f"{source.name}.{flavor}"
                    ),
                ),
                patch(
                    "scripts.font_ops.conversion.ThreadPoolExecutor"
                ) as executor_type,
            ):
                executor = MagicMock()
                executor.__enter__.return_value = executor
                executor.map.side_effect = run_map
                executor_type.return_value = executor

                outputs = convert_to_web(source_dir, target_dir, "woff2")

            executor_type.assert_called_once_with(max_workers=2)
            self.assertEqual(
                outputs,
                [
                    target_dir / "MapleMono-Bold.ttf.woff2",
                    target_dir / "MapleMono-Regular.ttf.woff2",
                ],
            )

    def test_woff2_worker_logs_the_font_it_converts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "MapleMono-Regular.ttf"
            output_dir = Path(tmp) / "Woff2"
            source.write_bytes(b"")
            output_dir.mkdir()
            font = MagicMock()

            with (
                patch("scripts.pipeline.TTFont", return_value=font) as ttfont,
                patch("scripts.pipeline.logger.info") as log_info,
            ):
                build_woff2_font_job(Woff2BuildJob(str(source), str(output_dir)))

            target = output_dir / "MapleMono-Regular.ttf.woff2"
            ttfont.assert_called_once_with(source, recalcTimestamp=False)
            self.assertEqual(font.flavor, "woff2")
            font.save.assert_called_once_with(target, reorderTables=False)
            font.close.assert_called_once()
            log_info.assert_called_once_with("Saved WOFF2 font to %s", target)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from concurrent.futures import Executor
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

from scripts.cjk.config import (
    CJKBuildConfig,
    CJKDownloadConfig,
    CJKOutputConfig,
    CJKSourceConfig,
)
from scripts.cjk.outlines import (
    convert_cff_master_files_to_glyf_tables_parallel,
    detect_outline_format,
)
from scripts.cjk.builder import CJKBuilder, create_font_executor
from scripts.config.resolver import BuildConfigResolver
from scripts.font_ops.fonttools import TTFont
from scripts.utils.errors import CJKSourceUnavailable


def make_config(output_dir: Path) -> CJKBuildConfig:
    source_path = output_dir / "source.ttf"
    source_path.write_bytes(b"source")
    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=source_path,
            masters={100: {"wght": 100}, 400: {"wght": 400}, 800: {"wght": 800}},
            download=CJKDownloadConfig(
                url="https://example.com/source.7z",
                path_in_archive="source.ttf",
            ),
        ),
        output=CJKOutputConfig(dir=output_dir),
    )


class CJKExecutorOwnershipTest(unittest.TestCase):
    def test_pool_size_one_uses_inline_execution(self) -> None:
        with patch("scripts.cjk.builder.create_process_executor") as create_process:
            executor = create_font_executor(1)
            future = executor.submit(lambda: "done")

        self.assertEqual(future.result(), "done")
        create_process.assert_not_called()

    def test_builder_resolves_source_before_creating_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder = CJKBuilder(
                make_config(Path(tmp)), BuildConfigResolver().load_defaults()
            )
            download = builder.config.source.download
            assert download is not None

            with (
                patch(
                    "scripts.cjk.builder.resolve_cached_download",
                    side_effect=FileNotFoundError("download failed"),
                ) as resolve_source,
                patch("scripts.cjk.builder.create_font_executor") as create_executor,
                self.assertRaisesRegex(CJKSourceUnavailable, "download failed"),
            ):
                builder.build()

            resolve_source.assert_called_once_with(
                "CJK source font",
                builder.config.source.path,
                download.url,
                "github.com",
                path_in_archive="source.ttf",
            )
            create_executor.assert_not_called()

    def test_builder_does_not_close_a_caller_owned_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = cast(Executor, MagicMock())
            builder = CJKBuilder(
                make_config(Path(tmp)),
                BuildConfigResolver().load_defaults(),
                executor,
            )

            with (
                patch.object(
                    builder,
                    "_build_regular_variable_font",
                    side_effect=RuntimeError("stop"),
                ),
                self.assertRaisesRegex(RuntimeError, "stop"),
            ):
                builder.build()

            cast(MagicMock, executor).shutdown.assert_not_called()

    def test_builder_closes_an_executor_it_creates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = MagicMock()
            builder = CJKBuilder(
                make_config(Path(tmp)), BuildConfigResolver().load_defaults()
            )

            with (
                patch(
                    "scripts.cjk.builder.create_font_executor", return_value=executor
                ),
                patch.object(
                    builder,
                    "_build_regular_variable_font",
                    side_effect=RuntimeError("stop"),
                ),
                self.assertRaisesRegex(RuntimeError, "stop"),
            ):
                builder.build()

            executor.shutdown.assert_called_once_with(
                wait=True,
                cancel_futures=True,
            )

    def test_cff_chunks_reuse_the_caller_owned_executor(self) -> None:
        executor = cast(Executor, MagicMock())
        future = MagicMock()
        future.result.return_value = {}
        cast(MagicMock, executor).submit.return_value = future

        with patch(
            "scripts.cjk.outlines.build_glyf_table",
            side_effect=(MagicMock(), MagicMock(), MagicMock()),
        ):
            tables = convert_cff_master_files_to_glyf_tables_parallel(
                ("thin.otf", "regular.otf", "bold.otf"),
                [".notdef"],
                executor,
            )

        self.assertEqual(len(tables), 3)
        cast(MagicMock, executor).submit.assert_called_once()


class CJKOutlineDetectionTest(unittest.TestCase):
    def make_font(self, *tables: str) -> TTFont:
        return cast(TTFont, {table: object() for table in tables})

    def test_detects_glyf_outline(self) -> None:
        self.assertEqual(
            detect_outline_format(self.make_font("glyf"), "source.ttf"),
            "glyf",
        )

    def test_detects_cff2_outline(self) -> None:
        self.assertEqual(
            detect_outline_format(self.make_font("CFF2"), "source.otf"),
            "cff2",
        )

    def test_rejects_static_cff_outline(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "static CFF.*source.otf.*variable font containing glyf or CFF2",
        ):
            detect_outline_format(self.make_font("CFF "), "source.otf")

    def test_rejects_missing_outline(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "no supported outlines.*source.bin.*exactly one of glyf or CFF2",
        ):
            detect_outline_format(self.make_font("name"), "source.bin")

    def test_rejects_ambiguous_variable_outlines(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "both glyf and CFF2.*source.ttf.*exactly one",
        ):
            detect_outline_format(
                self.make_font("glyf", "CFF2"),
                "source.ttf",
            )


if __name__ == "__main__":
    unittest.main()

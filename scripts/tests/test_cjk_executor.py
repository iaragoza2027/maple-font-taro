from __future__ import annotations

from concurrent.futures import Executor
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

from scripts.cjk.models import CJKBuildConfig, CJKOutputConfig, CJKSourceConfig
from scripts.cjk.pipeline import CJKBuilder


def make_config(output_dir: Path) -> CJKBuildConfig:
    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=Path("source.ttf"),
            masters={100: {"wght": 100}, 400: {"wght": 400}, 800: {"wght": 800}},
        ),
        output=CJKOutputConfig(dir=output_dir),
    )


class CJKExecutorOwnershipTest(unittest.TestCase):
    def test_builder_does_not_close_a_caller_owned_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = cast(Executor, MagicMock())
            builder = CJKBuilder(make_config(Path(tmp)), executor)

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
            builder = CJKBuilder(make_config(Path(tmp)))

            with (
                patch(
                    "scripts.cjk.pipeline.create_font_executor", return_value=executor
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


if __name__ == "__main__":
    unittest.main()

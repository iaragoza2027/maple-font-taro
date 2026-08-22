from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

from scripts.pipeline.fontmake import (
    PreparedFontmakeSource,
    prepare_fontmake_sources,
)
from scripts.tests.pipeline_fixtures import (
    make_font_config,
    make_runtime_context,
)

if TYPE_CHECKING:
    from concurrent.futures import Executor


class PipelineFontmakeTest(unittest.TestCase):
    def test_prepare_sources_resolves_regular_vertical_metric(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            font_config = make_font_config()
            font_config.feature.line_height = 1.2
            runtime_context = make_runtime_context(tmp_path)
            executor_mock = MagicMock()
            executor_mock.map.return_value = (
                PreparedFontmakeSource(
                    "regular",
                    "regular.designspace",
                    (1100, -300),
                ),
                PreparedFontmakeSource(
                    "italic",
                    "italic.designspace",
                    (1080, -320),
                ),
            )

            context = prepare_fontmake_sources(
                font_config,
                runtime_context,
                cast("Executor", executor_mock),
            )

            self.assertEqual(runtime_context.resolved_vertical_metric, (1100, -300))
            self.assertEqual(len(context.sources), 2)
            jobs = executor_mock.map.call_args.args[1]
            self.assertEqual(
                {job.feature_file_path for job in jobs},
                {
                    runtime_context.feature_file_path(False),
                    runtime_context.feature_file_path(True),
                },
            )
            self.assertTrue(all(job.font_config is font_config for job in jobs))


if __name__ == "__main__":
    unittest.main()

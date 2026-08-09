from __future__ import annotations

import logging
import os
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from scripts.utils.logging import (
    TaskName,
    configure_logging,
    log_progress,
    log_task,
    log_task_complete,
    logger,
    set_log_task,
)


class LoggingConfigurationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.package_logger = logging.getLogger("scripts")
        self.original_handlers = list(self.package_logger.handlers)
        self.original_level = self.package_logger.level
        self.original_propagate = self.package_logger.propagate
        self.package_logger.handlers.clear()

    def tearDown(self) -> None:
        self.package_logger.handlers.clear()
        self.package_logger.handlers.extend(self.original_handlers)
        self.package_logger.setLevel(self.original_level)
        self.package_logger.propagate = self.original_propagate
        set_log_task("system")

    def test_default_configuration_uses_plain_stderr_format(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configure_logging()

        handlers = self.package_logger.handlers
        self.assertEqual(len(handlers), 1)
        formatter = handlers[0].formatter
        self.assertIsNotNone(formatter)
        assert formatter is not None
        self.assertEqual(formatter._fmt, "%(message)s")
        self.assertEqual(self.package_logger.level, logging.INFO)
        self.assertFalse(self.package_logger.propagate)

    def test_invalid_log_level_warns_and_falls_back_to_info(self) -> None:
        stderr = StringIO()
        with (
            patch.dict(os.environ, {"MAPLE_LOG_LEVEL": "verbose"}, clear=True),
            redirect_stderr(stderr),
        ):
            configure_logging()

        self.assertEqual(self.package_logger.level, logging.INFO)
        self.assertEqual(
            stderr.getvalue(),
            "[WARNING] [system] Invalid MAPLE_LOG_LEVEL='VERBOSE'; using INFO\n",
        )

    def test_reconfiguration_reuses_the_project_handler(self) -> None:
        with patch.dict(os.environ, {"MAPLE_LOG_LEVEL": "DEBUG"}, clear=True):
            configure_logging()
            configure_logging()

        self.assertEqual(len(self.package_logger.handlers), 1)
        self.assertEqual(self.package_logger.level, logging.DEBUG)

    def test_task_context_is_inherited_by_regular_logs(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            configure_logging()
            log_task(TaskName.WOFF2, "Converting static fonts to WOFF2")
            logger.info("Saved WOFF2 font to fonts/Woff2/MapleMono-Regular.woff2")

        self.assertEqual(
            stderr.getvalue(),
            "[woff2] Converting static fonts to WOFF2\n"
            "[woff2] Saved WOFF2 font to "
            "fonts/Woff2/MapleMono-Regular.woff2\n",
        )

    def test_task_switch_inserts_one_unprefixed_blank_line(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            configure_logging()
            log_task(TaskName.PREPARE, "Preparing sources")
            log_task(TaskName.TTF, "Building TTF fonts")

        self.assertEqual(
            stderr.getvalue(),
            "[prepare] Preparing sources\n\n[ttf] Building TTF fonts\n",
        )

    def test_task_completion_includes_duration_and_summary(self) -> None:
        stderr = StringIO()
        with (
            redirect_stderr(stderr),
            patch(
                "scripts.utils.logging.time.monotonic",
                side_effect=(10.0, 12.5),
            ),
        ):
            configure_logging()
            started_at = log_task(TaskName.PREPARE, "Prepare font sources")
            log_task_complete(started_at, "2 sources")

        self.assertEqual(
            stderr.getvalue(),
            "[prepare] Prepare font sources\n[prepare] Done in 2.50s (2 sources)\n",
        )

    def test_debug_uses_the_compact_prefix(self) -> None:
        stderr = StringIO()
        with (
            patch.dict(os.environ, {"MAPLE_LOG_LEVEL": "DEBUG"}, clear=True),
            redirect_stderr(stderr),
        ):
            configure_logging()
            set_log_task(TaskName.FONTMAKE)
            logger.debug("Saved font to output.ttf")

        self.assertEqual(
            stderr.getvalue(),
            "> Saved font to output.ttf\n",
        )

    def test_progress_refreshes_the_same_log_line(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            configure_logging()
            set_log_task("download")
            log_progress("Downloading archive.zip: %s%%", 25)
            log_progress("Downloading archive.zip: %s%%", 100, complete=True)

        self.assertEqual(
            stderr.getvalue(),
            "\r[download] Downloading archive.zip: 25%"
            "\r[download] Downloading archive.zip: 100%\n",
        )


if __name__ == "__main__":
    unittest.main()

"""Project logging configuration for command-line entrypoints."""

from __future__ import annotations

from contextvars import ContextVar
import logging
import os
from typing import Any


ENVIRONMENT_VARIABLE = "MAPLE_LOG_LEVEL"
DEFAULT_LEVEL_NAME = "INFO"
_HANDLER_NAME = "maple-font-stderr"
_VALID_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
logger = logging.getLogger("scripts")
logger.addHandler(logging.NullHandler())
_current_task: ContextVar[str] = ContextVar("maple_log_task", default="system")


class LevelSeparatedFormatter(logging.Formatter):
    """Separate adjacent log groups when their severity changes."""

    def __init__(self) -> None:
        super().__init__("[%(levelname)s] [%(task)s] %(message)s")
        self.previous_level: int | None = None
        self.previous_task: str | None = None

    def format(self, record: logging.LogRecord) -> str:
        task = str(getattr(record, "task", "system"))
        if not hasattr(record, "task"):
            setattr(record, "task", task)
        message = super().format(record)
        separator = ""
        if self.previous_level is not None and (
            self.previous_level != record.levelno or task != self.previous_task
        ):
            separator = "\n"
        self.previous_level = record.levelno
        self.previous_task = task
        return separator + message


class TaskContextFilter(logging.Filter):
    """Attach the active task to records that do not set one explicitly."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "task"):
            record.task = _current_task.get()
        return True


def configure_logging() -> None:
    """Configure the project logger without changing third-party logging."""
    requested_level = os.environ.get(ENVIRONMENT_VARIABLE, DEFAULT_LEVEL_NAME).upper()
    level = _VALID_LEVELS.get(requested_level, logging.INFO)

    handler = next(
        (
            candidate
            for candidate in logger.handlers
            if candidate.get_name() == _HANDLER_NAME
        ),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        handler.set_name(_HANDLER_NAME)
        handler.setFormatter(LevelSeparatedFormatter())
        handler.addFilter(TaskContextFilter())
        logger.addHandler(handler)

    logger.setLevel(level)
    logger.propagate = False

    if requested_level not in _VALID_LEVELS:
        logger.warning(
            "Invalid %s=%r; using %s",
            ENVIRONMENT_VARIABLE,
            requested_level,
            DEFAULT_LEVEL_NAME,
        )


def set_log_task(task: str) -> None:
    """Set the task label inherited by subsequent log records in this worker."""
    _current_task.set(task)


def log_task(task: str, message: str, *args: Any) -> None:
    """Start a named task and retain its label for subsequent log records."""
    set_log_task(task)
    logger.info(message, *args)

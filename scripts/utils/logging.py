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
_last_started_task: ContextVar[str | None] = ContextVar(
    "maple_last_started_log_task", default=None
)


class TaskContextFilter(logging.Filter):
    """Attach the active task to records that do not set one explicitly."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "task"):
            record.task = _current_task.get()
        return True


def configure_logging() -> None:
    """Configure the project logger without changing third-party logging."""
    _current_task.set("system")
    _last_started_task.set(None)
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
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] [%(task)s] %(message)s")
        )
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


def _write_blank_line() -> None:
    """Write a task separator without manufacturing an empty log record."""
    for handler in logger.handlers:
        if handler.get_name() != _HANDLER_NAME:
            continue
        handler.acquire()
        try:
            stream = getattr(handler, "stream", None)
            if stream is not None:
                stream.write("\n")
                stream.flush()
        finally:
            handler.release()


def log_progress(message: str, *args: Any, complete: bool = False) -> None:
    """Refresh one INFO progress record in place on the project log stream."""
    if not logger.isEnabledFor(logging.INFO):
        return
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __file__,
        0,
        message,
        args,
        None,
    )
    for handler in logger.handlers:
        if handler.get_name() != _HANDLER_NAME or not handler.filter(record):
            continue
        handler.acquire()
        try:
            stream = getattr(handler, "stream", None)
            if stream is not None:
                stream.write(f"\r{handler.format(record)}")
                if complete:
                    stream.write("\n")
                stream.flush()
        finally:
            handler.release()


def log_task(task: str, message: str, *args: Any) -> None:
    """Start a named task and retain its label for subsequent log records."""
    previous_task = _last_started_task.get()
    if previous_task is not None and previous_task != task:
        _write_blank_line()
    set_log_task(task)
    _last_started_task.set(task)
    logger.info(message, *args)

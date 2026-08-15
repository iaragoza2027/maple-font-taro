from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.utils.logging import logger

if TYPE_CHECKING:
    import argparse


VARIABLE_OUTPUT_DIR = Path("fonts/variable")
SOURCE_DIR = Path("sources")
BUILDER_CONFIG = Path("sources/config.yaml")
FONTBAKERY_ARGS = (
    "check-googlefonts",
    "--ghmarkdown",
    "fonts/report.md",
    "fonts/variable/*.ttf",
)
INTERPOLATABLE_LOGGER_NAME = "fontTools.varLib.interpolatable"


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser(
        "googlefonts",
        help="Regenerate designspaces and build Google Fonts assets",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild UFO + designspace from Glyphs source files before building variable fonts",
    )
    parser.add_argument(
        "--qa",
        action="store_true",
        help="Clean variable outputs, build, and run FontBakery QA",
    )
    return parser


def _regenerate_designspace() -> None:
    """Regenerate the gftools input designspaces from the exported Glyphs files."""
    from scripts.task.designspace import generate_designspaces

    generate_designspaces(SOURCE_DIR, SOURCE_DIR)


def _run_gftools_builder() -> None:
    """Run gftools' builder entrypoint without spawning a second uv process."""
    from gftools.builder import main as builder_main

    original_cwd = Path.cwd()
    exit_code = 0
    try:
        try:
            exit_code = builder_main([str(BUILDER_CONFIG)])
        except SystemExit as error:
            exit_code = error.code
    finally:
        os.chdir(original_cwd)

    if exit_code not in (None, 0):
        raise SystemExit(exit_code)


def _run_fontbakery() -> None:
    """Run FontBakery with argv equivalent to the documented command."""
    from fontbakery.cli import main as fontbakery_main

    interpolatable_logger = logging.getLogger(INTERPOLATABLE_LOGGER_NAME)
    previous_log_level = interpolatable_logger.level
    interpolatable_logger.setLevel(logging.WARNING)
    original_argv = sys.argv
    try:
        sys.argv = ["fontbakery", *FONTBAKERY_ARGS]
        result = fontbakery_main()
    finally:
        sys.argv = original_argv
        interpolatable_logger.setLevel(previous_log_level)

    if result:
        raise SystemExit(result)


def run(args: argparse.Namespace) -> None:
    if args.rebuild:
        _regenerate_designspace()

    if args.qa and VARIABLE_OUTPUT_DIR.exists():
        logger.info("Clean Google Fonts variable output: path=%s", VARIABLE_OUTPUT_DIR)
        shutil.rmtree(VARIABLE_OUTPUT_DIR)

    _run_gftools_builder()

    if args.qa:
        _run_fontbakery()

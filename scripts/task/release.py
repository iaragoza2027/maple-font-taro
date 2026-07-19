from __future__ import annotations

import argparse
import os
import re
import shutil
from typing import Callable

from scripts.font_ops.fonttools import TTFont

from scripts.pipeline import main as build_main
from scripts.font_ops.conversion import convert_to_web
from scripts.utils.files import (
    join_path,
    write_json,
)
from scripts.utils.process import run as run_command
from scripts.font_ops.names import default_weight_map
from scripts.utils.version import project_version
from scripts.utils.logging import logger


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser("release", help="Release new version")
    parser.add_argument("type", choices=["major", "minor"], help="Bump version type")
    parser.add_argument("--dry", action="store_true", help="Dry run")
    return parser


def format_fontsource_name(filename: str):
    match = re.match(r"MapleMono-(.*)\.(.*)$", filename.replace(".ttf", ""))
    if not match:
        return None

    style = match.group(1)
    if style.endswith("Italic") and style != "Italic":
        base_style = style[:-6]
    else:
        base_style = style

    weight = default_weight_map.get(
        base_style.lower(), default_weight_map.get("regular", 400)
    )
    suffix = "italic" if "italic" in style.lower() else "normal"
    return f"maple-mono-latin-{weight}-{suffix}.{match.group(2)}"


def format_woff2_name(filename: str):
    return filename.replace(".ttf.woff2", "-VF.woff2")


def rename_woff_files(dir_path: str, fn: Callable[[str], str | None]):
    for filename in os.listdir(dir_path):
        if not filename.endswith(".woff") and not filename.endswith(".woff2"):
            continue
        new_name = fn(filename)
        if new_name:
            os.rename(join_path(dir_path, filename), join_path(dir_path, new_name))
            logger.info(
                "Renamed release font: source=%s, target=%s", filename, new_name
            )


def next_version(current: str, bump: str) -> str:
    """Calculate the next project version without changing project files."""
    parts = [int(part) for part in current.split(".")]
    if len(parts) < 2:
        raise ValueError(f"Expected a major.minor project version, got: {current}")
    if bump == "major":
        return f"{parts[0] + 1}.0"
    if bump == "minor":
        return f"{parts[0]}.{parts[1] + 1}"
    raise ValueError(f"Unsupported version bump: {bump}")


def git_release_commit(tag, files):
    run_command(f"git add {' '.join(files)}")
    run_command(["git", "commit", "-m", f"Release {tag}"])
    run_command(f"git tag {tag}")
    logger.info("Committed release and created tag")

    run_command("git push origin")
    run_command(f"git push origin {tag}")
    logger.info("Pushed release to origin")


def write_unicode_map_json(font_path: str, output: str):
    font = TTFont(font_path)
    cmap = font.getBestCmap() or {}
    font_map = {
        f"{codepoint:04X}" if codepoint < 0x10000 else f"{codepoint:05X}": glyph
        for codepoint, glyph in cmap.items()
        if codepoint is not None
    }
    write_json(output, font_map)
    logger.info("Wrote font map: path=%s", output)
    font.close()


def release(type: str, dry: bool):
    tag = f"v{next_version(project_version(), type)}"
    choose = input(f"{'[DRY] ' if dry else ''}Tag {tag}? (Y or n) ")
    if choose != "" and choose.lower() != "y":
        logger.info("Release aborted")
        return

    if not dry:
        run_command(["uv", "version", "--bump", type])

    target_fontsource_dir = "cdn/fontsource"
    build_main(["--ttf-only", "--no-nerd-font", "--cn", "--no-hinted"], tag)

    shutil.rmtree("./cdn", ignore_errors=True)
    convert_to_web("./fonts/TTF", target_fontsource_dir, flavor="woff2")
    convert_to_web("./fonts/TTF", target_fontsource_dir, flavor="woff")
    rename_woff_files(target_fontsource_dir, format_fontsource_name)
    logger.info("Generated Fontsource files")

    dep_file = "requirements.txt"
    run_command(
        f"uv export --format requirements-txt --no-hashes --output-file {dep_file} --quiet"
    )

    shutil.copytree("./fonts/CN", "./cdn/cn")
    logger.info("Generated CN files")

    woff2_dir = "woff2/var"
    if os.path.exists(target_fontsource_dir):
        shutil.rmtree(woff2_dir)
    convert_to_web("./fonts/Variable", woff2_dir, flavor="woff2")
    rename_woff_files(woff2_dir, format_woff2_name)

    if dry:
        logger.info("Release dry run complete")
    else:
        git_release_commit(tag, ["woff2", dep_file, "pyproject.toml"])


def run(args: argparse.Namespace) -> None:
    release(args.type, args.dry)

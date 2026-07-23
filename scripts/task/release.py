from __future__ import annotations

import argparse
from dataclasses import dataclass
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
from scripts.font_ops.constant import INSTANCE_WEIGHT_MAPPING
from scripts.utils.version import project_version
from scripts.utils.logging import logger


@dataclass(frozen=True)
class ReleasePlan:
    tag: str
    build_args: tuple[str, ...]
    fontsource_dir: str = "cdn/fontsource"
    requirements_file: str = "requirements.txt"
    variable_woff2_dir: str = "woff2/var"

    def describe(self) -> str:
        return "\n".join(
            (
                f"Tag: {self.tag}",
                f"Build: build.py {' '.join(self.build_args)}",
                f"Fontsource output: {self.fontsource_dir}",
                f"Variable WOFF2 output: {self.variable_woff2_dir}",
                f"Requirements output: {self.requirements_file}",
            )
        )


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

    weight = INSTANCE_WEIGHT_MAPPING.get(
        base_style.lower(), INSTANCE_WEIGHT_MAPPING.get("regular", 400)
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


def create_release_plan(bump: str) -> ReleasePlan:
    return ReleasePlan(
        tag=f"v{next_version(project_version(), bump)}",
        build_args=("--ttf-only", "--no-nerd-font", "--cn", "--no-hinted"),
    )


def generate_release_assets(plan: ReleasePlan) -> None:
    build_main(list(plan.build_args), plan.tag)

    shutil.rmtree("./cdn", ignore_errors=True)
    convert_to_web("./fonts/TTF", plan.fontsource_dir, flavor="woff2")
    convert_to_web("./fonts/TTF", plan.fontsource_dir, flavor="woff")
    rename_woff_files(plan.fontsource_dir, format_fontsource_name)
    logger.info("Generated Fontsource files")

    run_command(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-hashes",
            "--output-file",
            plan.requirements_file,
            "--quiet",
        ]
    )

    shutil.copytree("./fonts/CN", "./cdn/cn")
    logger.info("Generated CN files")

    if os.path.exists(plan.fontsource_dir):
        shutil.rmtree(plan.variable_woff2_dir)
    convert_to_web("./fonts/Variable", plan.variable_woff2_dir, flavor="woff2")
    rename_woff_files(plan.variable_woff2_dir, format_woff2_name)


def publish_release(plan: ReleasePlan) -> None:
    git_release_commit(
        plan.tag,
        ["woff2", plan.requirements_file, "pyproject.toml"],
    )


def release(bump: str, dry: bool) -> None:
    plan = create_release_plan(bump)
    if dry:
        print(plan.describe())
        return

    choose = input(f"Tag {plan.tag}? (Y or n) ")
    if choose != "" and choose.lower() != "y":
        logger.info("Release aborted")
        return

    run_command(["uv", "version", "--bump", bump])
    generate_release_assets(plan)
    publish_release(plan)


def run(args: argparse.Namespace) -> None:
    release(args.type, args.dry)

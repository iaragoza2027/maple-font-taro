from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from source.py.utils import is_ci


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser(
        "publish", help="Publish the font archives to GitHub Release"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write changelog to release note file (auto write in CI)",
    )
    return parser


def get_output(cmd: list[str]) -> str:
    return subprocess.check_output(cmd).decode("utf-8").strip()


def publish(write: bool, dry: bool = not is_ci()):
    tag_list = get_output(["git", "tag", "--list", "--sort=committerdate"]).split("\n")
    prev_tag = tag_list[-2]
    tag = tag_list[-1]
    print(f"Tag: {prev_tag} -> {tag}")

    changelog = get_output(
        ["git", "log", "--pretty=format:- %s\n%b", f"{prev_tag}..{tag}"]
    )

    template_path = Path(".github/release_template.md")
    title = " ".join(part.capitalize() for part in tag.split("-"))
    cmd = [
        "gh",
        "release",
        "create",
        tag,
        "release/**/*.*",
        "--notes-file",
        template_path.as_posix(),
        "-t",
        title,
        "--draft",
    ]

    template = (
        template_path.read_text()
        .replace("<!-- changelog -->", changelog)
        .replace(
            "https://<url>",
            f"https://github.com/subframe7536/maple-font/releases/download/{tag}",
        )
    )
    if write or not dry:
        template_path.write_text(template)

    if dry:
        print(f"changelog:\n{changelog}\n\nRun command: {' '.join(cmd)}")
    else:
        subprocess.run(cmd, check=True)


def run(args: argparse.Namespace) -> None:
    publish(args.write)

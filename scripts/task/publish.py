from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from scripts.utils.process import is_ci
from scripts.utils.logging import logger


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser(
        "publish", help="Publish the font archives to GitHub Release"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write changelog to release note file (auto write in CI)",
    )
    parser.add_argument(
        "--tag",
        help="Git tag to publish (defaults to the unique tag pointing at HEAD)",
    )
    return parser


def get_output(cmd: list[str]) -> str:
    return subprocess.check_output(cmd).decode("utf-8").strip()


def resolve_release_tags(tag: str | None) -> tuple[str, str]:
    if tag is not None:
        try:
            get_output(["git", "rev-parse", "--verify", f"refs/tags/{tag}"])
        except subprocess.CalledProcessError as error:
            raise ValueError(f"Unknown release tag: {tag}") from error
    else:
        tags = get_output(["git", "tag", "--points-at", "HEAD"]).splitlines()
        if not tags:
            raise ValueError("No release tag points at HEAD; pass --tag explicitly")
        if len(tags) > 1:
            raise ValueError(
                "Multiple release tags point at HEAD; pass --tag explicitly: "
                + ", ".join(tags)
            )
        tag = tags[0]

    prev_tag = get_output(["git", "describe", "--tags", "--abbrev=0", f"{tag}^"])
    return prev_tag, tag


def publish(write: bool, tag: str | None = None, dry: bool = not is_ci()):
    prev_tag, tag = resolve_release_tags(tag)
    logger.info("Publish release: previous_tag=%s, tag=%s", prev_tag, tag)

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
    publish(args.write, args.tag)

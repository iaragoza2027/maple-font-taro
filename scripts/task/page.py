from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from python_minifier import minify

from scripts.feature import (
    get_cv_cn_version_info,
    get_cv_italic_version_info,
    get_cv_version_info,
    get_ss_version_info,
    get_total_feat_ts,
)
from scripts.utils import (
    joinPaths,
    read_json,
    read_text,
    run as run_command,
    write_json,
    write_text,
)


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser("page", help="Update landing page data")
    parser.add_argument("--woff2", action="store_true", help="Generate new woff2 fonts")
    parser.add_argument(
        "--sync", action="store_true", help="Sync latest page data and commit"
    )
    return parser


def run_git_command(args: list[str], cwd=None, check=True):
    try:
        result = subprocess.run(
            args, cwd=cwd, check=check, capture_output=True, text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as error:
        print(
            f"Error: Failed to execute {' '.join(args)} in {cwd or os.getcwd()}: {error.stderr}"
        )
        sys.exit(1)


def update_page(
    submodule_path: str,
    var_dir: str,
    woff2: bool = False,
    sync: bool = False,
) -> None:
    abs_submodule_path = os.path.abspath(submodule_path)

    if not os.path.exists(abs_submodule_path):
        print(
            f"Error: Submodule {submodule_path} does not exist, please run `git submodule update --init` first"
        )
        sys.exit(1)

    if sync:
        run_git_command(["git", "submodule", "update", "--remote"])
        print("Checkout main")
        run_git_command(["git", "checkout", "main"], cwd=abs_submodule_path)
        run_git_command(["git", "pull"], cwd=abs_submodule_path)
        print("Sync remote")

    print("Update features")
    feature_data_base = joinPaths(submodule_path, "data", "features")
    os.makedirs(feature_data_base, exist_ok=True)
    write_json(joinPaths(feature_data_base, "cv.json"), get_cv_version_info())
    write_json(joinPaths(feature_data_base, "cn.json"), get_cv_cn_version_info())
    write_json(
        joinPaths(feature_data_base, "italic.json"), get_cv_italic_version_info()
    )
    write_json(joinPaths(feature_data_base, "ss.json"), get_ss_version_info())
    write_text(joinPaths(feature_data_base, "features.ts"), get_total_feat_ts())

    print("Update config")
    data = read_json("config.json")
    del data["$schema"]
    write_json(joinPaths(submodule_path, "data", "config.json"), data)

    print("Update script")
    script_content = read_text(joinPaths("scripts", "in_browser.py"))
    write_text(
        joinPaths(submodule_path, "data", "script.py"),
        "# Source: https://github.com/subframe7536/maple-font/blob/variable/scripts/in_browser.py\n"
        + minify(script_content),
    )

    if woff2:
        print("Update woff2")
        font_dir = joinPaths(submodule_path, "public", "fonts")
        run_command("python build.py --ttf-only --no-nerd-font --least-styles")
        run_command(f"ftcli converter ft2wf -f woff2 {var_dir}")
        shutil.rmtree(font_dir, ignore_errors=True)
        os.makedirs(font_dir, exist_ok=True)
        for filename in os.listdir(var_dir):
            if filename.endswith(".woff2"):
                os.rename(
                    joinPaths(var_dir, filename),
                    joinPaths(font_dir, filename.replace(".ttf.woff2", "-VF.woff2")),
                )

    if sync:
        run_git_command(["git", "add", "."], cwd=abs_submodule_path)
        print("Commit submodule")
        run_git_command(
            ["git", "commit", "-m", "Update landing page data"], cwd=abs_submodule_path
        )
        print("Update remote submodule")
        run_git_command(["git", "push", "origin", "main"], cwd=abs_submodule_path)
        run_git_command(["git", "submodule", "update", "--remote"])
        run_git_command(["git", "add", "."])
        print("Commit main")
        run_git_command(["git", "commit", "-m", "sync landing page"])
        print("Update remote main")
        run_git_command(["git", "push", "origin"])


def run(args: argparse.Namespace) -> None:
    update_page("./maple-font-page", "./fonts/Variable", args.woff2, args.sync)

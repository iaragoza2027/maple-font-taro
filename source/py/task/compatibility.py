from __future__ import annotations

import argparse
from os import path
import shutil

from source.py.cjk.builder import build_cjk_fonts
from source.py.cjk.presets import build_preset_config
from source.py.cjk.vf import save_merged_variable_fonts


def _warn_legacy(name: str, replacement: str) -> None:
    print(f"⚠️ `{name}` is deprecated. Use `{replacement}` instead.")


def _build_preset_alias(preset: str, vf_only: bool) -> None:
    build_cjk_fonts(build_preset_config(preset), vf_only=vf_only)


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    cn = subparsers.add_parser("cn", help="Compatibility alias for `task.py cjk --preset cn`")
    cn.add_argument("--pull", action="store_true", help=argparse.SUPPRESS)
    cn.add_argument("--rebuild", action="store_true", help=argparse.SUPPRESS)
    cn.set_defaults(_command_handler=run)

    jp = subparsers.add_parser("jp", help="Compatibility alias for `task.py cjk --preset jp`")
    jp.add_argument(
        "--vf-only",
        action="store_true",
        help="only rebuild variable font and skip static font generation",
    )
    jp.set_defaults(_command_handler=run)

    merge_vf = subparsers.add_parser("merge-cn-vf", help="Merge Variable fonts with CN extension")
    merge_vf.add_argument(
        "--output", type=str, default="./fonts/Variable-CN", help="Output directory"
    )
    merge_vf.set_defaults(_command_handler=run)

    browser = subparsers.add_parser("browser-test", help="Run in-browser test helper")
    browser.add_argument(
        "--zip-path",
        default="./fonts/archive/MapleMono-NF-CN-unhinted.zip",
        help="Archive path used for browser test",
    )
    browser.set_defaults(_command_handler=run)
    return None


def run(args: argparse.Namespace) -> None:
    if args.command == "cn":
        _warn_legacy("task.py cn", "task.py cjk --preset cn")
        if args.pull or args.rebuild:
            print("⚠️ Legacy `--pull` / `--rebuild` flags are ignored by the compatibility alias.")
        _build_preset_alias("cn", vf_only=False)
        return

    if args.command == "jp":
        _warn_legacy("task.py jp", "task.py cjk --preset jp")
        _build_preset_alias("jp", vf_only=args.vf_only)
        return

    if args.command == "merge-cn-vf":
        _warn_legacy("task.py merge-cn-vf", "build.py --cjk cn --cjk-format variable")
        save_merged_variable_fonts(args.output, locale="cn")
        return

    print("Test only")
    from source.py.in_browser import main

    zip_path = args.zip_path
    if not path.exists(zip_path):
        print("No zip file, please run `uv run build.py --archive` first")
        return
    test_path = zip_path.replace(".zip", "-test.zip")
    shutil.copy(zip_path, test_path)
    main(
        test_path,
        zip_path.replace(".zip", "-result.zip"),
        {"cv01": "1", "cv02": "1"},
    )

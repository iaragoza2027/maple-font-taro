from __future__ import annotations

import argparse

from scripts.cjk.builder import build_cjk_fonts
from scripts.cjk.config import (
    add_cjk_arguments,
    apply_cli_overrides,
    apply_unicode_override,
)
from scripts.cjk.presets import build_preset_config, list_presets


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser("cjk", help="Build preset or custom CJK base font")
    parser.add_argument(
        "--preset",
        choices=list(list_presets()),
        help="Use a built-in CJK preset",
    )
    add_cjk_arguments(parser)
    return parser


def run(args: argparse.Namespace) -> None:
    if args.preset:
        config = build_preset_config(args.preset)
        config = apply_cli_overrides(config, args)
        config = apply_unicode_override(config, args.unicodes)
        build_cjk_fonts(config, args.vf_only)
        return

    from scripts.cjk.builder import build_cjk_from_args

    build_cjk_from_args(args)

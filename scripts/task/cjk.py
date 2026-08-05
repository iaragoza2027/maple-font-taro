from __future__ import annotations

import argparse
from typing import cast

from scripts.cjk.builder import build_cjk_fonts
from scripts.cjk.presets import CJKPresetId, build_preset_config, list_presets
from scripts.cjk.resolver import (
    add_cjk_arguments,
    apply_cli_overrides,
    apply_unicode_override,
)
from scripts.config.resolver import resolve_default_build_config
from scripts.utils.downloads import github_mirror_from_config


def parse_preset_ids(value: str) -> tuple[CJKPresetId, ...]:
    """Parse and validate comma-separated built-in CJK preset IDs."""
    preset_ids = tuple(part.strip() for part in value.split(","))
    valid_preset_ids = list_presets()
    invalid_preset_ids = tuple(
        preset_id for preset_id in preset_ids if preset_id not in valid_preset_ids
    )
    if invalid_preset_ids:
        valid = ", ".join(valid_preset_ids)
        invalid = ", ".join(invalid_preset_ids)
        raise argparse.ArgumentTypeError(
            f"invalid CJK preset(s): {invalid}; choose from: {valid}"
        )
    return tuple(cast(CJKPresetId, preset_id) for preset_id in preset_ids)


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser("cjk", help="Build preset or custom CJK base font")
    parser.add_argument(
        "--preset",
        type=parse_preset_ids,
        metavar="PRESET[,PRESET...]",
        help="Use one or more built-in CJK presets",
    )
    add_cjk_arguments(parser)
    return parser


def run(args: argparse.Namespace) -> None:
    github_mirror = github_mirror_from_config()
    if args.preset:
        for preset_id in args.preset:
            config = build_preset_config(preset_id)
            config = apply_cli_overrides(config, args)
            config = apply_unicode_override(config, args.unicodes)
            build_cjk_fonts(
                config,
                resolve_default_build_config(),
                args.vf_only,
                github_mirror=github_mirror,
            )
        return

    from scripts.cjk.builder import build_cjk_from_args

    build_cjk_from_args(args, github_mirror)

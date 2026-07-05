"""CLI entrypoint and argument parsing for the Maple build pipeline."""

from __future__ import annotations

import argparse

from source.py.build.config import (
    WIDTH_MAP,
    normalize_build_formats,
    parse_scale_factor,
)
from source.py.build.pipeline import FONT_VERSION, main as run_pipeline


def build_parser(version: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="✨ Builder and optimizer for Maple Mono",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"Maple Mono Builder v{version or FONT_VERSION}",
    )
    parser.add_argument(
        "-d",
        "--dry",
        dest="dry",
        action="store_true",
        help="Output config and exit",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Add `Debug` suffix to family name and faster build",
    )

    feature_group = parser.add_argument_group("Feature Options")
    feature_group.add_argument(
        "-n",
        "--normal",
        dest="normal",
        action="store_true",
        help="Use normal preset, just like `JetBrains Mono` with slashed zero",
    )
    feature_group.add_argument(
        "--feat",
        type=lambda x: x.strip().split(","),
        help="Freeze font features, split by `,` (e.g. `--feat zero,cv01,ss07,ss08`). No effect on variable format",
    )
    feature_group.add_argument(
        "--apply-fea-file",
        default=None,
        action="store_true",
        help="Load feature file from `source/features/{regular,italic}.fea` to variable font",
    )
    hint_group = feature_group.add_mutually_exclusive_group()
    hint_group.add_argument(
        "--hinted",
        dest="hinted",
        default=None,
        action="store_true",
        help="Use hinted font as base font in NF / CN / NF-CN (default)",
    )
    hint_group.add_argument(
        "--no-hinted",
        dest="hinted",
        default=None,
        action="store_false",
        help="Use unhinted font as base font in NF / CN / NF-CN",
    )
    liga_group = feature_group.add_mutually_exclusive_group()
    liga_group.add_argument(
        "--liga",
        dest="liga",
        default=None,
        action="store_true",
        help="Preserve all the ligatures (default)",
    )
    liga_group.add_argument(
        "--no-liga",
        dest="liga",
        default=None,
        action="store_false",
        help="Remove all the ligatures",
    )
    feature_group.add_argument(
        "--keep-infinite-arrow",
        default=None,
        action="store_true",
        help="(Deprecated) Keep infinite arrow ligatures in hinted font (Removed by default)",
    )
    feature_group.add_argument(
        "--infinite-arrow",
        default=None,
        action="store_true",
        dest="infinite_arrow",
        help="Enable infinite arrow ligatures (Disabled in hinted font by default)",
    )
    feature_group.add_argument(
        "--remove-tag-liga",
        default=None,
        action="store_true",
        help="Remove plain text tag ligatures like `[TODO]`",
    )
    feature_group.add_argument(
        "--line-height",
        type=float,
        help="Scale factor for line height (e.g., 1.1)",
    )
    feature_group.add_argument(
        "--width",
        type=str,
        choices=WIDTH_MAP.keys(),
        default=None,
        help="Set glyph width: default (600), narrow (550), slim (500)",
    )

    build_group = parser.add_argument_group("Build Options")
    build_group.add_argument(
        "--format",
        dest="formats",
        type=normalize_build_formats,
        help="Build base formats as a comma-separated list: ttf,otf,woff2",
    )
    build_group.add_argument(
        "--ttf-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    build_group.add_argument(
        "--least-styles",
        action="store_true",
        help="Only build Regular / Bold / Italic / BoldItalic style",
    )
    build_group.add_argument(
        "--cache",
        action="store_true",
        help="Reuse font cache of TTF, OTF, and Woff2 formats",
    )
    build_group.add_argument(
        "--archive",
        action="store_true",
        help="Build font archives with config and license. If it has the `--cache` flag, only archive NF and CN formats",
    )

    nerd_font_group = parser.add_argument_group("Nerd Font Options")
    nf_group = nerd_font_group.add_mutually_exclusive_group()
    nf_group.add_argument(
        "--nf",
        "--nerd-font",
        dest="nerd_font",
        default=None,
        action="store_true",
        help="Build Nerd-Font version (default)",
    )
    nf_group.add_argument(
        "--no-nf",
        "--no-nerd-font",
        dest="nerd_font",
        default=None,
        action="store_false",
        help="Do not build the Nerd-Font version",
    )
    nerd_font_group.add_argument(
        "--nf-mono",
        action="store_true",
        help="Make Nerd Font icons' width fixed",
    )
    nerd_font_group.add_argument(
        "--nf-propo",
        action="store_true",
        help="Make Nerd Font icons' width variable, override `--nf-mono`",
    )
    nerd_font_group.add_argument(
        "--font-patcher",
        action="store_true",
        help="Force the use of Nerd Font Patcher to build NF format",
    )

    cjk_group = parser.add_argument_group("CJK Options")
    cjk_group.add_argument(
        "--cjk",
        action="append",
        help="Build Maple Mono + CJK extended fonts for locales: cn, jp, tc, kr. Repeat or use comma-separated values.",
    )
    cjk_group.add_argument(
        "--cjk-format",
        choices=("static", "variable"),
        default="static",
        help="Persist CJK-extended output as static fonts (default) or merged variable fonts.",
    )
    cjk_group.add_argument(
        "--cjk-narrow",
        action="store_true",
        help="Apply narrow CJK spacing to the selected locales.",
    )
    cjk_group.add_argument(
        "--cjk-scale-factor",
        type=parse_scale_factor,
        help="Scale factor for selected CJK locales. Format: <factor> or <width_factor>,<height_factor>.",
    )

    deprecated_cn_group = parser.add_argument_group("Deprecated CN Options")
    cn_group = deprecated_cn_group.add_mutually_exclusive_group()
    cn_group.add_argument(
        "--cn",
        dest="cn",
        default=None,
        action="store_true",
        help="Deprecated alias for `--cjk cn`.",
    )
    cn_group.add_argument(
        "--no-cn",
        dest="cn",
        default=None,
        action="store_false",
        help="Deprecated alias for removing `cn` from the selected CJK locales.",
    )
    deprecated_cn_group.add_argument(
        "--cn-narrow",
        action="store_true",
        help="Deprecated alias for `--cjk-narrow` when targeting `cn`.",
    )
    deprecated_cn_group.add_argument(
        "--cn-scale-factor",
        type=parse_scale_factor,
        help="Deprecated alias for `--cjk-scale-factor` when targeting `cn`.",
    )
    deprecated_cn_group.add_argument(
        "--cn-both",
        action="store_true",
        help="Deprecated compatibility mode for building both `Maple Mono CN` and `Maple Mono NF CN`.",
    )
    deprecated_cn_group.add_argument(
        "--cn-rebuild",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    return parser


def parse_args(
    args: list[str] | None = None, version: str | None = None
) -> argparse.Namespace:
    return build_parser(version=version).parse_args(args)


def main(args: list[str] | None = None, version: str | None = None) -> None:
    run_pipeline(parse_args(args, version=version), version=version)


__all__ = ["build_parser", "parse_args", "main"]

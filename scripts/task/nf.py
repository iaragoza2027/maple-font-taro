from __future__ import annotations

import argparse
import json
from os import environ, path, remove
from urllib.request import urlopen

from fontTools.subset import Subsetter
from fontTools.varLib import TTFont

from scripts.utils.downloads import check_font_patcher
from scripts.utils.process import get_font_forge_bin, run as run_command
from scripts.font_ops.metadata import set_monospace_metadata
from scripts.font_ops.names import (
    del_font_name,
    set_font_name,
)


BASE_FONT_PATH = "fonts/TTF/MapleMono-Regular.ttf"
FAMILY_NAME = "Maple Mono"
FONT_FORGE_BIN = get_font_forge_bin()


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser("nf", help="Build Nerd-Font base font")
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Do not check version and update if available",
    )
    return parser


def parse_codes_from_json(data) -> list[int]:
    try:
        return [
            int(f"0x{value['code']}", 16)
            for key, value in data.items()
            if isinstance(value, dict) and "code" in value
        ]
    except json.JSONDecodeError:
        print("Invalide JSON")
        exit(1)


def update_config_json(config_path: str, version: str):
    with open(config_path, "r+", encoding="utf-8") as file:
        data = json.load(file)

        if "nerd_font" in data:
            data["nerd_font"]["version"] = version

        file.seek(0)
        json.dump(data, file, ensure_ascii=False, indent=2)


def check_update():
    current_version = None
    with open("./config.json", "r", encoding="utf-8") as file:
        data = json.load(file)
        current_version = data["nerd_font"]["version"]

    latest_version = current_version
    print("Getting latest version from remote...")
    with urlopen(
        "https://api.github.com/repos/ryanoasis/nerd-fonts/releases/latest"
    ) as response:
        data = json.loads(response.read().decode("utf-8").split("\n")[0])
        for key in data:
            if key == "tag_name":
                latest_version = str(data[key])[1:]
                break

        if latest_version == current_version:
            print("✨ Current version match latest version")
            if not check_font_patcher(latest_version):
                print("Font-Patcher not exist and fail to download, exit")
                exit(1)
            return

        print(
            f"Current version {current_version} not match latest version {latest_version}, update"
        )
        if not check_font_patcher(latest_version, environ.get("GITHUB", "github.com")):
            print("Fail to update Font-Patcher, exit")
            exit(1)
        update_config_json("./config.json", latest_version)
        update_config_json("./source/preset-normal.json", latest_version)


def get_nerd_font_patcher_args(mono: bool, propo: bool = False):
    nf_args = [
        FONT_FORGE_BIN,
        "FontPatcher/font-patcher",
        "-l",
        "-c",
        "--careful",
    ]
    if mono:
        nf_args += ["--mono"]
    elif propo:
        nf_args += ["--variable-width-glyphs"]
    return nf_args


def get_font_suffix(mono: bool, propo: bool) -> str:
    if mono and propo:
        raise ValueError(
            "Cannot build both `mono` and `propo` glyphs versions simultaneously."
        )
    if mono:
        return "Mono"
    if propo:
        return "Propo"
    return ""


def build_nf(mono: bool, propo: bool = False):
    suffix = get_font_suffix(mono, propo)
    nf_args = get_nerd_font_patcher_args(mono, propo)

    nf_file_name = "NerdFont" + suffix
    style_name = "Regular"

    run_command(nf_args + [BASE_FONT_PATH])
    output_path = f"{FAMILY_NAME.replace(' ', '')}{nf_file_name}-{style_name}.ttf"
    nf_font = TTFont(output_path)
    remove(output_path)

    full_family_name = f"{FAMILY_NAME} NF Base{f' {suffix}' if suffix else ''}"
    set_font_name(nf_font, full_family_name, 1)
    set_font_name(nf_font, style_name, 2)
    set_font_name(nf_font, f"{full_family_name} {style_name}", 4)
    set_font_name(
        nf_font,
        f"{FAMILY_NAME.replace(' ', '-')}-NF-Base{f'-{suffix}' if suffix else ''}-{style_name}",
        6,
    )
    del_font_name(nf_font, 16)
    del_font_name(nf_font, 17)

    return nf_font


def subset(mono: bool, propo: bool, unicodes: list[int]):
    font = build_nf(mono, propo)
    subsetter = Subsetter()
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)

    suffix = get_font_suffix(mono, propo)
    output_path = f"source/MapleMono-NF-Base{f'-{suffix}' if suffix else ''}.ttf"

    if not propo:
        set_monospace_metadata(font)
    font.save(output_path)
    font.close()


def nerd_font(no_update: bool):
    if not path.exists(BASE_FONT_PATH):
        print(
            "font not exist, please run this command first:\n\n    python build.py --ttf-only --no-nerd-font --least-styles\n"
        )
        exit(1)

    if not no_update:
        check_update()

    with open("./FontPatcher/glyphnames.json", "r", encoding="utf-8") as file:
        unicodes = parse_codes_from_json(json.load(file))
        subset(mono=False, propo=False, unicodes=unicodes)
        subset(mono=True, propo=False, unicodes=unicodes)
        subset(mono=False, propo=True, unicodes=unicodes)


def run(args: argparse.Namespace) -> None:
    nerd_font(args.no_update)

from __future__ import annotations

from typing import Protocol

from scripts.font_ops.fonttools import TTFont
from scripts.utils.logging import logger


class _NerdFontConfig(Protocol):
    @property
    def version(self) -> str: ...


class FontNameConfig(Protocol):
    @property
    def version_str(self) -> str: ...

    @property
    def beta(self) -> str | None: ...

    @property
    def nerd_font(self) -> _NerdFontConfig: ...

    @property
    def freeze_config_str(self) -> str: ...


def set_font_name(font: TTFont, name: str, id: int, mac: bool | None = None):
    font["name"].setName(name, nameID=id, platformID=3, platEncID=1, langID=0x409)
    if mac:
        font["name"].setName(name, nameID=id, platformID=1, platEncID=0, langID=0x0)


def get_font_name(font: TTFont, id: int) -> str:
    return (
        font["name"]
        .getName(nameID=id, platformID=3, platEncID=1, langID=0x409)
        .__str__()
    )


def del_font_name(font: TTFont, id: int):
    font["name"].removeNames(nameID=id)


def parse_style_name(style_name_compact: str):
    is_italic = style_name_compact.endswith("Italic")

    style_name = style_name_compact
    if is_italic and style_name_compact[0] != "I":
        style_name = style_name_compact[:-6] + " Italic"

    base_subfamily_list = ["Regular", "Bold", "Italic", "BoldItalic"]
    if style_name_compact in base_subfamily_list:
        return "", style_name, style_name, True, is_italic
    return (
        " " + style_name_compact.replace("Italic", ""),
        "Italic" if is_italic else "Regular",
        style_name,
        False,
        is_italic,
    )


def update_font_names(
    font: TTFont,
    font_config: FontNameConfig,
    family_name: str,
    style_name: str,
    full_name: str,
    postscript_name: str,
    is_skip_subfamily: bool,
    preferred_family_name: str | None = None,
    preferred_style_name: str | None = None,
    narrow: bool = False,
    variable: bool = False,
):
    font["name"].removeNames(platformID=1)
    if len(family_name) > 31:
        logger.warning(
            "Family name may exceed legacy Windows limits: family=%s, length=%s",
            family_name,
            len(family_name),
        )
    set_font_name(font, family_name, 1)
    set_font_name(font, style_name, 2)
    suffix = ""
    if variable:
        suffix += "Variable;"
    if "NF" in postscript_name:
        suffix += f"NF{font_config.nerd_font.version};"
    if "CN" in postscript_name and narrow:
        suffix += "Narrow;"

    suffix += font_config.freeze_config_str
    beta_str = f"-{font_config.beta}" if font_config.beta else ""
    unique_identifier = (
        f"{font_config.version_str}{beta_str};SUBF;{postscript_name};"
        f"2026;FL830;{suffix}"
    )

    set_font_name(font, unique_identifier, 3)
    set_font_name(font, full_name, 4)
    set_font_name(font, font_config.version_str, 5)
    set_font_name(font, postscript_name, 6)

    if not is_skip_subfamily and preferred_family_name and preferred_style_name:
        set_font_name(font, preferred_family_name, 16)
        set_font_name(font, preferred_style_name, 17)

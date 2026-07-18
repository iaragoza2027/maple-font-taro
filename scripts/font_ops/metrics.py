from __future__ import annotations

from typing import cast

from fontTools.ttLib import TTFont

from scripts.font_ops.fonttools_types import OS2Table
from scripts.utils.logging import logger


def verify_glyph_width(
    font: TTFont, expect_widths: list[int], file_name: str | None = None
):
    result = []
    for name in font.getGlyphNames():
        width, _ = font["hmtx"][name]
        if width not in expect_widths:
            result.append([name, width])

    if not result:
        logger.debug("Verified glyph widths: file=%s", file_name)
        return

    unexpected_glyphs = "\n".join(f"{name}  =>  {width}" for name, width in result)
    raise Exception(
        f"{file_name or 'The font'} may contains glyphs that width is not in {expect_widths}, which may broke monospace rule.\n{unexpected_glyphs}"
    )


def adjust_line_height(
    font: TTFont, factor: float, metric: tuple[float, float]
) -> None:
    if "hhea" not in font:
        raise ValueError("No hhea table found.")
    if "OS/2" not in font:
        raise ValueError("No OS/2 table found.")

    asc, desc = metric
    ascender_ratio = asc / (asc - desc)
    target_total_height = int(round(factor * (asc - desc)))
    new_ascender = int(round(target_total_height * ascender_ratio))
    new_descender = new_ascender - target_total_height

    logger.debug(
        "Update vertical metrics: ascender=%s, descender=%s",
        new_ascender,
        new_descender,
    )
    font["head"].yMax = new_ascender
    font["head"].yMin = new_descender
    font["hhea"].ascent = new_ascender
    font["hhea"].descent = new_descender
    os2 = cast(OS2Table, font["OS/2"])
    os2.sTypoAscender = new_ascender
    os2.sTypoDescender = new_descender
    os2.usWinAscent = new_ascender
    os2.usWinDescent = -new_descender

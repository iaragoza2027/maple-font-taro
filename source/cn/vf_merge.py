#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fontTools.ttLib import TTFont


FontInput = str | Path | TTFont


def load_font(font: FontInput) -> TTFont:
    if isinstance(font, TTFont):
        return font
    return TTFont(font)


def variable_axes(font: TTFont) -> list[tuple[str, float, float, float]]:
    if "fvar" not in font:
        raise ValueError("Font is not variable: missing fvar table.")

    return [
        (axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue)
        for axis in font["fvar"].axes
    ]


def unicode_cmap(font: TTFont) -> dict[int, str]:
    result: dict[int, str] = {}
    for table in font["cmap"].tables:
        if table.isUnicode():
            result.update(table.cmap)
    return result


def validate_fonts(base: TTFont, extra: TTFont) -> None:
    required_tables = ("glyf", "hmtx", "cmap", "fvar", "gvar")
    for table_tag in required_tables:
        if table_tag not in base:
            raise ValueError(f"Base font is missing required table: {table_tag}")
        if table_tag not in extra:
            raise ValueError(f"Extra font is missing required table: {table_tag}")

    if base["head"].unitsPerEm != extra["head"].unitsPerEm:
        raise ValueError(
            "Cannot merge fonts with different UPEM values: "
            f"{base['head'].unitsPerEm} != {extra['head'].unitsPerEm}"
        )

    base_axes = variable_axes(base)
    extra_axes = variable_axes(extra)
    if base_axes != extra_axes:
        raise ValueError(
            "Cannot merge fonts with different variable axes: "
            f"{base_axes} != {extra_axes}"
        )


def merge_cmap(base: TTFont, extra: TTFont, added_glyphs: set[str]) -> int:
    base_codepoints = set(unicode_cmap(base))
    extra_entries = {
        codepoint: glyph_name
        for codepoint, glyph_name in unicode_cmap(extra).items()
        if glyph_name in added_glyphs and codepoint not in base_codepoints
    }

    for table in base["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(extra_entries)

    return len(extra_entries)


def merge_glyph_tables(base: TTFont, extra: TTFont) -> list[str]:
    base_glyph_order = base.getGlyphOrder()
    extra_glyph_order = extra.getGlyphOrder()
    base_glyphs = set(base_glyph_order)
    glyphs_to_add = [
        glyph_name for glyph_name in extra_glyph_order if glyph_name not in base_glyphs
    ]

    base_glyf = base["glyf"]
    extra_glyf = extra["glyf"]
    base_hmtx = base["hmtx"]
    extra_hmtx = extra["hmtx"]
    base_gvar = base["gvar"]
    extra_gvar = extra["gvar"]

    for glyph_name in glyphs_to_add:
        base_glyf.glyphs[glyph_name] = deepcopy(extra_glyf.glyphs[glyph_name])
        base_hmtx.metrics[glyph_name] = extra_hmtx.metrics[glyph_name]
        base_gvar.variations[glyph_name] = deepcopy(
            extra_gvar.variations.get(glyph_name, [])
        )

    base.setGlyphOrder(base_glyph_order + glyphs_to_add)
    base["maxp"].numGlyphs = len(base.getGlyphOrder())
    return glyphs_to_add


def recalculate(font: TTFont) -> None:
    font["hhea"].numberOfHMetrics = len(font["hmtx"].metrics)
    font["hhea"].recalc(font)

    if "OS/2" in font:
        font["OS/2"].recalcAvgCharWidth(font)
        font["OS/2"].recalcUnicodeRanges(font)
        font["OS/2"].recalcCodePageRanges(font)


def merge_vf(base_font: FontInput, extra_font: FontInput) -> tuple[TTFont, list[str], int]:
    base = load_font(base_font)
    extra = load_font(extra_font)

    validate_fonts(base, extra)
    added_glyphs = merge_glyph_tables(base, extra)
    added_codepoints = merge_cmap(base, extra, set(added_glyphs))
    recalculate(base)

    return base, added_glyphs, added_codepoints

from __future__ import annotations

from typing import cast

from fontTools.merge import Merger
from fontTools.ttLib import TTFont

from scripts.font_ops.fonttools_types import HheaTable
from scripts.utils.logging import logger


def merge_ttfonts(
    base_font_path: str, extra_font_path: str, use_pyftmerge: bool = False
) -> TTFont:
    if use_pyftmerge:
        return Merger().merge([base_font_path, extra_font_path])

    try:
        base_font = TTFont(base_font_path)
        extra_font = TTFont(extra_font_path)
        base_glyf = base_font["glyf"]
        extra_glyf = extra_font["glyf"]
        base_glyph_order = base_font.getGlyphOrder()
        extra_glyph_order = extra_font.getGlyphOrder()
        base_hmtx = base_font["hmtx"] if "hmtx" in base_font else None
        extra_hmtx = extra_font["hmtx"] if "hmtx" in extra_font else None
        base_glyph_names = set(base_glyph_order)
        glyphs_to_add: list[str] = []

        for glyph_name in extra_glyph_order:
            if glyph_name in base_glyph_names:
                continue
            base_glyf.glyphs[glyph_name] = extra_glyf.glyphs[glyph_name]
            if base_hmtx and extra_hmtx and glyph_name in extra_hmtx.metrics:
                base_hmtx.metrics[glyph_name] = extra_hmtx.metrics[glyph_name]
            elif base_hmtx:
                base_hmtx.metrics[glyph_name] = (0, 0)
            glyphs_to_add.append(glyph_name)

        if not glyphs_to_add:
            logger.debug("Skip font merge because no new glyphs were found")
            return base_font

        updated_glyph_order = base_glyph_order + glyphs_to_add
        base_font.setGlyphOrder(updated_glyph_order)
        base_font["maxp"].numGlyphs = len(updated_glyph_order)

        if "cmap" in extra_font and "cmap" in base_font:
            base_cmap = base_font["cmap"].getBestCmap()
            extra_cmap = extra_font["cmap"].getBestCmap()
            if base_cmap and extra_cmap:
                for codepoint, glyph_name in extra_cmap.items():
                    if glyph_name in glyphs_to_add and codepoint not in base_cmap:
                        base_cmap[codepoint] = glyph_name

        if "hhea" in base_font:
            if base_hmtx:
                cast(HheaTable, base_font["hhea"]).numberOfHMetrics = len(
                    base_hmtx.metrics
                )
            cast(HheaTable, base_font["hhea"]).recalc(base_font)
        return base_font
    except Exception:
        raise

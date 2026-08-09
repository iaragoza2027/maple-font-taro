from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scripts.font_ops.fonttools import TTFont


def _supports_codepoint(table_format: int, codepoint: int) -> bool:
    if table_format == 0:
        return codepoint <= 0xFF
    if table_format in (2, 4, 6):
        return codepoint <= 0xFFFF
    if table_format in (10, 12, 13):
        return codepoint <= 0x10FFFF
    return codepoint <= 0xFFFF


def merge_cmap_entries(
    base_font: TTFont,
    extra_font: TTFont,
    glyph_names: Iterable[str],
) -> set[int]:
    """Merge new Unicode mappings supported by each base cmap subtable."""
    allowed_glyphs = set(glyph_names)
    base_codepoints = set(base_font["cmap"].getBestCmap() or {})
    entries = {
        codepoint: glyph_name
        for codepoint, glyph_name in (extra_font["cmap"].getBestCmap() or {}).items()
        if glyph_name in allowed_glyphs and codepoint not in base_codepoints
    }

    merged_codepoints: set[int] = set()
    for table in base_font["cmap"].tables:
        if not table.isUnicode():
            continue
        supported_entries = {
            codepoint: glyph_name
            for codepoint, glyph_name in entries.items()
            if _supports_codepoint(table.format, codepoint)
        }
        table.cmap.update(supported_entries)
        merged_codepoints.update(supported_entries)
    return merged_codepoints

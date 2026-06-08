#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from fontTools.ttLib import TTFont


DEFAULT_BASE_FONT = Path("source/MapleMono-CN-feature-VF.ttf")
DEFAULT_EXTRA_FONT = Path("source/cn/WenYuanRoundedSCVF-MapleCN.ttf")
DEFAULT_OUTPUT = Path("source/cn/WenYuanRounded-CN-VF.ttf")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge Maple Mono CN feature VF with WenYuanRounded Maple CN VF."
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=DEFAULT_BASE_FONT,
        help="Base variable font. Its names, features, and layout tables are preserved.",
    )
    parser.add_argument(
        "--extra",
        type=Path,
        default=DEFAULT_EXTRA_FONT,
        help="Variable font whose missing glyphs are appended to the base font.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print merge summary without writing the output font.",
    )
    return parser.parse_args()


def variable_axes(font: TTFont) -> list[tuple[str, float, float, float]]:
    if "fvar" not in font:
        raise ValueError("Font is not variable: missing fvar table.")

    return [
        (axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue)
        for axis in font["fvar"].axes
    ]


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

    conflicts = (set(base.getGlyphOrder()) & set(extra.getGlyphOrder())) - {".notdef"}
    if conflicts:
        sample = ", ".join(sorted(conflicts)[:20])
        raise ValueError(f"Glyph name conflicts found: {sample}")


def unicode_cmap(font: TTFont) -> dict[int, str]:
    result: dict[int, str] = {}
    for table in font["cmap"].tables:
        if table.isUnicode():
            result.update(table.cmap)
    return result


def merge_cmap(base: TTFont, extra: TTFont, added_glyphs: set[str]) -> int:
    base_codepoints = set(unicode_cmap(base))
    extra_entries = {
        codepoint: glyph_name
        for codepoint, glyph_name in unicode_cmap(extra).items()
        if glyph_name in added_glyphs and codepoint not in base_codepoints
    }

    for table in base["cmap"].tables:
        if not table.isUnicode():
            continue
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


def recalculate(base: TTFont) -> None:
    base["hhea"].numberOfHMetrics = len(base["hmtx"].metrics)
    base["hhea"].recalc(base)

    if "OS/2" in base:
        base["OS/2"].recalcAvgCharWidth(base)
        base["OS/2"].recalcUnicodeRanges(base)
        base["OS/2"].recalcCodePageRanges(base)


def merge_vf(base_path: Path, extra_path: Path) -> tuple[TTFont, list[str], int]:
    base = TTFont(base_path)
    extra = TTFont(extra_path)

    validate_fonts(base, extra)
    added_glyphs = merge_glyph_tables(base, extra)
    added_codepoints = merge_cmap(base, extra, set(added_glyphs))
    recalculate(base)

    return base, added_glyphs, added_codepoints


def print_summary(prefix: str, font: TTFont) -> None:
    print(f"{prefix} glyphs: {len(font.getGlyphOrder())}")
    print(f"{prefix} unicodes: {len(unicode_cmap(font))}")
    print(f"{prefix} axes: {variable_axes(font)}")


def main() -> None:
    args = parse_args()

    base, added_glyphs, added_codepoints = merge_vf(args.base, args.extra)
    print_summary("merged", base)
    print(f"added glyphs: {len(added_glyphs)}")
    print(f"added unicodes: {added_codepoints}")

    if args.dry_run:
        print("dry-run: output not written")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    base.save(args.output)
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()

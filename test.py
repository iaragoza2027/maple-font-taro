#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

from fontTools.misc.timeTools import timestampNow
from fontTools.ttLib import TTFont


DEFAULT_ANGLE = 10.0
DEFAULT_WIDTH_SCALE = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an oblique TTF from a regular TTF while preserving original spacing."
    )
    parser.add_argument("input", type=Path, help="Input TTF path.")
    parser.add_argument("output", type=Path, help="Output TTF path.")
    parser.add_argument(
        "-a",
        "--angle",
        type=float,
        default=DEFAULT_ANGLE,
        help=f"Right-leaning oblique angle in degrees. Default: {DEFAULT_ANGLE:g}.",
    )
    parser.add_argument(
        "--recenter",
        action="store_true",
        help="Move each glyph back to its original bbox center after skewing.",
    )
    parser.add_argument(
        "--width-scale",
        type=float,
        default=DEFAULT_WIDTH_SCALE,
        help=(
            "Scale outlines horizontally around the glyph advance center without "
            f"changing advance widths. Default: {DEFAULT_WIDTH_SCALE:g}."
        ),
    )
    parser.add_argument(
        "--preserve-lsb",
        action="store_true",
        help="Keep original hmtx left side bearings instead of matching transformed xMin.",
    )
    parser.add_argument(
        "--update-metadata",
        action="store_true",
        help="Mark the output font as italic in post/head/OS/2/hhea metadata.",
    )
    parser.add_argument(
        "--offset",
        type=float,
        default=0.0,
        help="Extra horizontal outline offset after skewing and recentering.",
    )
    return parser.parse_args()


def ot_round(value: float) -> int:
    return (
        int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))
    )


def bbox_center_x(glyph) -> float:
    return (glyph.xMin + glyph.xMax) / 2


def ensure_simple_glyph(glyf_table, glyph):
    if glyph.isComposite():
        coordinates, end_points, flags = glyph.getCoordinates(glyf_table)
        glyph.coordinates = coordinates
        glyph.endPtsOfContours = end_points
        glyph.flags = flags
        glyph.numberOfContours = len(end_points)
        if hasattr(glyph, "components"):
            del glyph.components


def skew_glyph(
    glyf_table,
    glyph,
    skew_factor: float,
    width_scale: float,
    advance_width: int,
    recenter: bool,
    offset: float,
) -> bool:
    if getattr(glyph, "numberOfContours", 0) == 0 and not glyph.isComposite():
        return False

    ensure_simple_glyph(glyf_table, glyph)
    if getattr(glyph, "numberOfContours", 0) == 0:
        glyph.recalcBounds(glyf_table)
        return False

    original_center_x = bbox_center_x(glyph)
    glyph.coordinates.transform(((1, 0), (skew_factor, 1), (0, 0)))
    if width_scale != 1:
        center_x = advance_width / 2
        glyph.coordinates.transform(
            ((width_scale, 0), (0, 1), (center_x * (1 - width_scale), 0))
        )
    glyph.recalcBounds(glyf_table)

    x_shift = offset
    if recenter:
        x_shift += original_center_x - bbox_center_x(glyph)
    if x_shift:
        glyph.coordinates.translate((ot_round(x_shift), 0))
        glyph.recalcBounds(glyf_table)

    return True


def update_italic_metadata(font: TTFont, angle: float) -> None:
    italic_angle = -angle

    if "post" in font:
        font["post"].italicAngle = italic_angle

    if "head" in font:
        font["head"].macStyle |= 0x02
        font["head"].modified = timestampNow()

    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.fsSelection = (os2.fsSelection & ~0x40) | 0x01

    if "hhea" in font:
        font["hhea"].caretSlopeRise = 1000
        font["hhea"].caretSlopeRun = ot_round(math.tan(math.radians(angle)) * 1000)


def process_font(
    input_path: Path,
    output_path: Path,
    angle: float,
    width_scale: float,
    recenter: bool,
    offset: float,
    preserve_lsb: bool,
    update_metadata: bool,
) -> None:
    font = TTFont(input_path)
    if "glyf" not in font or "hmtx" not in font:
        raise ValueError("Only TrueType fonts with glyf and hmtx tables are supported.")

    skew_factor = math.tan(math.radians(angle))
    glyf_table = font["glyf"]
    hmtx = font["hmtx"]
    original_metrics = dict(hmtx.metrics)

    changed = 0
    for glyph_name in font.getGlyphOrder():
        glyph = glyf_table[glyph_name]
        advance_width, _ = original_metrics.get(glyph_name, (0, 0))
        if skew_glyph(
            glyf_table,
            glyph,
            skew_factor,
            width_scale,
            advance_width,
            recenter,
            offset,
        ):
            if not preserve_lsb:
                hmtx[glyph_name] = (advance_width, glyph.xMin)
            changed += 1

    for glyph_name, (advance_width, left_side_bearing) in original_metrics.items():
        if glyph_name not in hmtx.metrics:
            continue
        if preserve_lsb:
            hmtx[glyph_name] = (advance_width, left_side_bearing)
        else:
            hmtx[glyph_name] = (advance_width, hmtx[glyph_name][1])

    if update_metadata:
        update_italic_metadata(font, angle)
    elif "head" in font:
        font["head"].modified = timestampNow()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(output_path)
    font.close()

    print(f"input: {input_path}")
    print(f"output: {output_path}")
    print(f"angle: {angle:g}")
    print(f"skew factor: {skew_factor:.6f}")
    print(f"width scale: {width_scale:g}")
    print(f"recenter: {recenter}")
    print(f"preserve lsb: {preserve_lsb}")
    print(f"update metadata: {update_metadata}")
    print(f"changed glyphs: {changed}")


def main() -> None:
    args = parse_args()
    process_font(
        input_path=args.input,
        output_path=args.output,
        angle=args.angle,
        width_scale=args.width_scale,
        recenter=args.recenter,
        offset=args.offset,
        preserve_lsb=args.preserve_lsb,
        update_metadata=args.update_metadata,
    )


# width_scale / recenter / offset / preserve_lsb feature should removed
if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

from fontTools.ttLib import TTFont


DEFAULT_INPUT = Path("source/cn/WenYuanRounded-CN-VF.ttf")
DEFAULT_OUTPUT = Path("source/cn/WenYuanRounded-CN-VF-Italic.ttf")
DEFAULT_ITALIC_ANGLE = -10  # post.italicAngle convention: negative = right-leaning


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Make a font italic by applying skew transformation."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--angle",
        type=float,
        default=DEFAULT_ITALIC_ANGLE,
        help="Italic angle in degrees (negative for right-leaning, post table convention)",
    )
    return parser.parse_args()


def otRound(value: float) -> int:
    """Round half away from zero, as used by OpenType."""
    return (
        int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))
    )


def calculate_skew(italic_angle_deg: float) -> float:
    """
    Skew factor for the x-shear: new_x = x + y * skew.
    A negative italic angle (right-leaning) yields a positive skew factor.
    """
    return -math.tan(math.radians(italic_angle_deg))


def italic_name(value: str) -> str:
    if "Italic" in value:
        return value
    if value == "Regular":
        return "Italic"
    return f"{value} Italic"


def italic_postscript_name(value: str) -> str:
    if "Italic" in value:
        return value
    return f"{value}-Italic"


def set_name(font: TTFont, name_id: int, value: str) -> None:
    records = [record for record in font["name"].names if record.nameID == name_id]
    if not records:
        font["name"].setName(value, name_id, 3, 1, 0x409)
        return

    for record in records:
        font["name"].setName(
            value,
            name_id,
            record.platformID,
            record.platEncID,
            record.langID,
        )


def skew_glyph(font: TTFont, glyph_name: str, skew_factor: float) -> None:
    """Apply skew transformation to a single glyph."""
    glyf_table = font["glyf"]
    glyph = glyf_table[glyph_name]

    if glyph.isComposite():
        # Component placement offsets transform as: dx += dy * skew
        for component in glyph.components:
            if hasattr(component, "x") and hasattr(component, "y"):
                component.x += otRound(component.y * skew_factor)
    elif getattr(glyph, "numberOfContours", 0) > 0:
        if not hasattr(glyph, "coordinates") or glyph.coordinates is None:
            coordinates, _, _ = glyph.getCoordinates(glyf_table)
            glyph.coordinates = coordinates
        else:
            coordinates = glyph.coordinates

        # Apply skew: new_x = old_x + old_y * skew_factor
        for i in range(len(coordinates)):
            x, y = coordinates[i]
            coordinates[i] = (otRound(x + y * skew_factor), y)

    glyph.recalcBounds(glyf_table)


def skew_gvar(font: TTFont, skew_factor: float) -> None:
    """Apply the same shear to variation deltas: delta_x += delta_y * skew."""
    if "gvar" not in font:
        return

    for variations in font["gvar"].variations.values():
        for variation in variations:
            coordinates = variation.coordinates
            if coordinates is None:
                continue
            for i, delta in enumerate(coordinates):
                if delta is None:
                    continue
                dx, dy = delta
                coordinates[i] = (otRound(dx + dy * skew_factor), dy)


def update_italic_metadata(font: TTFont, italic_angle_deg: float) -> None:
    """Update font metadata to reflect italic style."""
    if "post" in font:
        font["post"].italicAngle = italic_angle_deg

    if "OS/2" in font:
        os2 = font["OS/2"]
        # Set ITALIC (bit 0), clear REGULAR (bit 6)
        os2.fsSelection = (os2.fsSelection & ~0x40) | 0x01

    if "head" in font:
        # Set italic bit (bit 1)
        font["head"].macStyle |= 0x02

    if "hhea" in font:
        hhea = font["hhea"]
        hhea.caretSlopeRise = 1000
        hhea.caretSlopeRun = otRound(-math.tan(math.radians(italic_angle_deg)) * 1000)

    name_table = font["name"]
    subfamily_name = name_table.getDebugName(2)
    full_name = name_table.getDebugName(4)
    postscript_name = name_table.getDebugName(6)
    preferred_style_name = name_table.getDebugName(17)

    if subfamily_name:
        set_name(font, 2, italic_name(subfamily_name))
    if full_name:
        set_name(font, 4, italic_name(full_name))
    if postscript_name:
        set_name(font, 6, italic_postscript_name(postscript_name))
    if preferred_style_name:
        set_name(font, 17, italic_name(preferred_style_name))


def make_italic(args: argparse.Namespace) -> TTFont:
    """Load font, apply italic transformation, balance spacing, and update metadata."""
    print(f"Loading font: {args.input}")
    font = TTFont(args.input)

    skew_factor = calculate_skew(args.angle)
    print(f"Italic angle: {args.angle} degrees")
    print(f"Skew factor: {skew_factor:.6f}")

    glyph_order = font.getGlyphOrder()
    print(f"Transforming {len(glyph_order)} glyphs...")

    for glyph_name in glyph_order:
        skew_glyph(font, glyph_name, skew_factor)

    print("Transforming variation deltas...")
    skew_gvar(font, skew_factor)

    print("Updating font metadata...")
    update_italic_metadata(font, args.angle)

    return font


def main() -> None:
    args = parse_args()
    font = make_italic(args)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    font.save(args.output)
    print(f"Italic font saved: {args.output}")


if __name__ == "__main__":
    main()

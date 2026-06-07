#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

from fontTools.ttLib import TTFont


DEFAULT_INPUT = Path("source/cn/WenYuanRoundedSCVF-MapleCN.ttf")
DEFAULT_OUTPUT = Path("source/cn/WenYuanRoundedSCVF-MapleCN-Italic.ttf")
DEFAULT_ITALIC_ANGLE = -10  # post.italicAngle convention: negative = right-leaning

# CJK ranges to balance
CJK_RANGES = (
    (0x2E80, 0x2EFF),
    (0x2F00, 0x2FDF),
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x3100, 0x312F),
    (0x31A0, 0x31EF),
    (0x3200, 0x33FF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F),
    (0xFF00, 0xFFEF),
)


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
    return int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))


def calculate_skew(italic_angle_deg: float) -> float:
    """
    Skew factor for the x-shear: new_x = x + y * skew.
    A negative italic angle (right-leaning) yields a positive skew factor.
    """
    return -math.tan(math.radians(italic_angle_deg))


def is_cjk(codepoint: int) -> bool:
    """Check if codepoint is in CJK ranges."""
    for start, end in CJK_RANGES:
        if start <= codepoint <= end:
            return True
    return False


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
            for i, delta in enumerate(coordinates):
                if delta is None:
                    continue
                dx, dy = delta
                coordinates[i] = (otRound(dx + dy * skew_factor), dy)


def balance_cjk_spacing_with_gvar(font: TTFont) -> int:
    """
    Balance side bearings for CJK glyphs after italic transformation.
    Also adjusts gvar deltas so spacing remains balanced across all weight instances.
    """
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    glyf = font["glyf"]
    has_gvar = "gvar" in font

    balanced_count = 0

    for codepoint, glyph_name in cmap.items():
        if not is_cjk(codepoint):
            continue

        if glyph_name not in hmtx.metrics or glyph_name not in glyf:
            continue

        advance, current_lsb = hmtx.metrics[glyph_name]
        glyph = glyf[glyph_name]

        # Skip glyphs without outlines
        if not hasattr(glyph, 'xMin') or not hasattr(glyph, 'xMax'):
            continue

        # Calculate what balanced LSB should be at default weight
        glyph_width = glyph.xMax - glyph.xMin
        total_spacing = advance - glyph_width
        balanced_lsb = total_spacing // 2

        # Calculate how much to shift the glyph horizontally
        shift = balanced_lsb - glyph.xMin

        if abs(shift) > 1:  # Only adjust if shift is significant
            # Shift the default outline
            if glyph.isComposite():
                for component in glyph.components:
                    if hasattr(component, "x"):
                        component.x += shift
            elif getattr(glyph, "numberOfContours", 0) > 0:
                coordinates = glyph.coordinates
                for i in range(len(coordinates)):
                    x, y = coordinates[i]
                    coordinates[i] = (x + shift, y)

            # Recalculate bounds after shifting
            glyph.recalcBounds(glyf)

            # Update the LSB in hmtx to match new xMin
            hmtx.metrics[glyph_name] = (advance, glyph.xMin)

            # Now handle gvar deltas
            # Calculate how xMin and xMax change with the variation
            if has_gvar and glyph_name in font["gvar"].variations:
                coordinates = glyph.coordinates
                if not coordinates:
                    continue

                variations = font["gvar"].variations[glyph_name]

                for variation in variations:
                    if not variation.coordinates:
                        continue

                    # Find which points define xMin and xMax in the default outline
                    x_coords = [coord[0] for coord in coordinates]
                    default_xMin = min(x_coords)
                    default_xMax = max(x_coords)

                    # Calculate xMin and xMax after applying deltas
                    varied_x_coords = []
                    for i, (x, y) in enumerate(coordinates):
                        delta = variation.coordinates[i]
                        if delta is None:
                            varied_x_coords.append(x)
                        else:
                            dx, dy = delta
                            varied_x_coords.append(x + dx)

                    varied_xMin = min(varied_x_coords)
                    varied_xMax = max(varied_x_coords)

                    # Calculate how much xMin and xMax changed
                    delta_xMin = varied_xMin - default_xMin
                    delta_xMax = varied_xMax - default_xMax

                    # The centering offset: shift to keep glyph centered as it expands
                    # If xMin moves left by -10 and xMax moves right by +20,
                    # we need to shift everything right by ((-10) + 20) / 2 = +5
                    centering_offset = -otRound((delta_xMin + delta_xMax) / 2)

                    if abs(centering_offset) > 1:
                        for i, delta in enumerate(variation.coordinates):
                            if delta is None:
                                continue
                            dx, dy = delta
                            variation.coordinates[i] = (dx + centering_offset, dy)

            balanced_count += 1

    return balanced_count


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


def make_italic(args: argparse.Namespace) -> TTFont:
    """Load font, apply italic transformation, balance spacing, and update metadata."""
    print(f"Loading font: {args.input}")
    font = TTFont(args.input)

    skew_factor = calculate_skew(args.angle)
    print(f"Italic angle: {args.angle}°")
    print(f"Skew factor: {skew_factor:.6f}")

    glyph_order = font.getGlyphOrder()
    print(f"Transforming {len(glyph_order)} glyphs...")

    for glyph_name in glyph_order:
        skew_glyph(font, glyph_name, skew_factor)

    print("Transforming variation deltas...")
    skew_gvar(font, skew_factor)

    print("Balancing CJK glyph spacing across all weights...")
    balanced_count = balance_cjk_spacing_with_gvar(font)
    print(f"Balanced {balanced_count} CJK glyphs")

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

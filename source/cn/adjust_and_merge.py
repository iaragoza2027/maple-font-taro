#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont

from vf_utils import change_default_master, merge_vf, weight_axis


INSTANCE_WEIGHT_VALUES = {
    "Thin": 100.0,
    "ExtraLight": 210.0,
    "Light": 320.0,
    "Regular": 400.0,
    "Medium": 490.0,
    "SemiBold": 570.0,
    "Bold": 680.0,
    "ExtraBold": 800.0,
}


def drop_intermediate_masters(font: TTFont, target_default: float) -> TTFont:
    """Drop the internal Regular weight master while keeping named instances."""
    axis = weight_axis(font)
    old_default = axis.defaultValue if axis else target_default
    print(f"Changing default from {old_default} to {target_default:g}")
    return change_default_master(
        font,
        target_default,
        instance_weights=INSTANCE_WEIGHT_VALUES,
        default_style="Regular",
    )


def prepare_base_font(input_path: Path, target_default: float = 100) -> TTFont:
    """Adjust the default weight of base font to match target."""
    print(f"Preparing base font: {input_path}")
    font = TTFont(input_path)

    # Check current axis
    if "fvar" not in font:
        print("No fvar table found")
        return font

    axis = weight_axis(font)
    if not axis:
        print("No wght axis found")
        return font

    print(
        f"Current wght axis: {axis.minValue}/{axis.defaultValue}/{axis.maxValue}"
    )

    # Drop intermediate masters and shift default
    font = drop_intermediate_masters(font, target_default)
    axis = weight_axis(font)

    print(
        f"Adjusted wght axis: {axis.minValue}/{axis.defaultValue}/{axis.maxValue}\n"
    )

    return font


def merge_fonts(base: TTFont, extra: TTFont, output_path: Path) -> None:
    """Merge two variable fonts."""
    # Check axes and adjust base font to match extra
    base_axis = next((ax for ax in base["fvar"].axes if ax.axisTag == "wght"), None)
    extra_axis = next((ax for ax in extra["fvar"].axes if ax.axisTag == "wght"), None)

    if base_axis and extra_axis:
        print(
            f"Base axis before: wght {base_axis.minValue}/{base_axis.defaultValue}/{base_axis.maxValue}"
        )
        print(
            f"Extra axis: wght {extra_axis.minValue}/{extra_axis.defaultValue}/{extra_axis.maxValue}"
        )

        # Drop intermediate masters by shifting default to match extra
        if base_axis.defaultValue != extra_axis.defaultValue:
            base = drop_intermediate_masters(base, extra_axis.defaultValue)
            base_axis = weight_axis(base)

        print(
            f"Base axis after: wght {base_axis.minValue}/{base_axis.defaultValue}/{base_axis.maxValue}"
        )

    base_glyphs = set(base.getGlyphOrder())
    merged_font, added_glyphs, added_codepoints = merge_vf(base, extra)

    print(f"Base glyphs: {len(base_glyphs)}")
    print(f"Extra glyphs to add: {len(added_glyphs)}")
    print(f"Added {added_codepoints} new Unicode mappings")

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_font.save(output_path)
    print(f"Saved: {output_path}")
    print(f"Total glyphs: {len(merged_font.getGlyphOrder())}")


if __name__ == "__main__":
    # Prepare base font with adjusted default weight and merge
    base = prepare_base_font(
        Path("fonts/Variable/MapleMono[wght].ttf"), target_default=100
    )
    merge_fonts(
        base,
        TTFont("source/cn/WenYuanRounded-CN-VF.ttf"),
        Path("fonts/MapleMono-CN-VF.ttf"),
    )

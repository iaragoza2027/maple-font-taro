#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont

from vf_utils import merge_vf, weight_axis


EXPECTED_WEIGHT_AXIS = (100.0, 400.0, 800.0)


def require_weight_axis_values(
    font: TTFont, input_path: Path | None = None
) -> tuple[float, float, float]:
    axis = weight_axis(font)
    if not axis:
        suffix = f": {input_path}" if input_path else ""
        raise ValueError(f"Font is missing wght axis{suffix}")
    return (float(axis.minValue), float(axis.defaultValue), float(axis.maxValue))


def load_variable_font(input_path: Path) -> TTFont:
    """Load a variable font and require the Regular master to be default."""
    print(f"Preparing variable font: {input_path}")
    font = TTFont(input_path)

    if "fvar" not in font:
        raise ValueError(f"Font is missing fvar table: {input_path}")

    values = require_weight_axis_values(font, input_path)
    print(f"Current wght axis: {values[0]:g}/{values[1]:g}/{values[2]:g}\n")
    if values != EXPECTED_WEIGHT_AXIS:
        expected = "/".join(f"{value:g}" for value in EXPECTED_WEIGHT_AXIS)
        actual = "/".join(f"{value:g}" for value in values)
        raise ValueError(f"Expected wght axis {expected}, got {actual}: {input_path}")
    return font


def merge_fonts(base: TTFont, extra: TTFont, output_path: Path) -> None:
    """Merge two variable fonts."""
    base_axis = require_weight_axis_values(base)
    extra_axis = require_weight_axis_values(extra)
    print(f"Base axis: wght {base_axis[0]:g}/{base_axis[1]:g}/{base_axis[2]:g}")
    print(f"Extra axis: wght {extra_axis[0]:g}/{extra_axis[1]:g}/{extra_axis[2]:g}")

    base_glyphs = set(base.getGlyphOrder())
    merged_font, added_glyphs, added_codepoints = merge_vf(base, extra)

    print(f"Base glyphs: {len(base_glyphs)}")
    print(f"Extra glyphs to add: {len(added_glyphs)}")
    print(f"Added {added_codepoints} new Unicode mappings")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_font.save(output_path)
    print(f"Saved: {output_path}")
    print(f"Total glyphs: {len(merged_font.getGlyphOrder())}")


if __name__ == "__main__":
    base = load_variable_font(Path("fonts/Variable/MapleMono[wght].ttf"))
    merge_fonts(
        base,
        load_variable_font(Path("source/cn/WenYuanRounded-CN-VF.ttf")),
        Path("fonts/MapleMono-CN-VF.ttf"),
    )

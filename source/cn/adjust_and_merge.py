#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.instancer import OverlapMode, instantiateVariableFont


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


def get_weight_axis(font: TTFont):
    if "fvar" not in font:
        return None
    return next((axis for axis in font["fvar"].axes if axis.axisTag == "wght"), None)


def get_gvar_coordinates(font: TTFont, glyph_name: str):
    glyf = font["glyf"]
    h_metrics = font["hmtx"].metrics
    v_metrics = font["vmtx"].metrics if "vmtx" in font else None
    coordinates, _ = glyf._getCoordinatesAndControls(
        glyph_name, h_metrics, v_metrics
    )
    return coordinates


def rebuild_linear_gvar(font: TTFont, max_weight_font: TTFont) -> None:
    """Replace intermediate weight deltas with a single Thin-to-ExtraBold delta."""
    if "gvar" not in font:
        return

    variations = {}
    for glyph_name in font.getGlyphOrder():
        default_coordinates = get_gvar_coordinates(font, glyph_name)
        max_coordinates = get_gvar_coordinates(max_weight_font, glyph_name)

        if len(default_coordinates) != len(max_coordinates):
            raise ValueError(
                f"Point count mismatch for {glyph_name}: "
                f"{len(default_coordinates)} != {len(max_coordinates)}"
            )

        delta = [
            (int(round(max_x - default_x)), int(round(max_y - default_y)))
            for (default_x, default_y), (max_x, max_y) in zip(
                default_coordinates, max_coordinates
            )
        ]
        if any(dx or dy for dx, dy in delta):
            variations[glyph_name] = [
                TupleVariation({"wght": (0.0, 1.0, 1.0)}, delta)
            ]

    font["gvar"].variations = variations


def update_instance_weight_values(font: TTFont) -> None:
    if "fvar" not in font:
        return

    for instance in font["fvar"].instances:
        style_name = font["name"].getDebugName(instance.subfamilyNameID)
        weight_value = INSTANCE_WEIGHT_VALUES.get(style_name)
        if weight_value is not None:
            instance.coordinates["wght"] = weight_value


def update_stat_default_weight(font: TTFont, default_style: str = "Regular") -> None:
    if "STAT" not in font:
        return

    stat = font["STAT"].table
    axis_records = getattr(getattr(stat, "DesignAxisRecord", None), "Axis", [])
    weight_axis_indices = {
        index for index, axis in enumerate(axis_records) if axis.AxisTag == "wght"
    }
    axis_values = getattr(getattr(stat, "AxisValueArray", None), "AxisValue", None)
    if not weight_axis_indices or not axis_values:
        return

    for axis_value in axis_values:
        axis_index = getattr(axis_value, "AxisIndex", None)
        if axis_index not in weight_axis_indices:
            continue

        value_name_id = getattr(axis_value, "ValueNameID", None)
        value_name = font["name"].getDebugName(value_name_id) if value_name_id else None
        if value_name == default_style:
            axis_value.Flags = 2
        else:
            axis_value.Flags = 0


def drop_intermediate_masters(font: TTFont, target_default: float) -> TTFont:
    """Drop the internal Regular weight master while keeping named instances."""
    if "fvar" not in font or "gvar" not in font:
        return font

    weight_axis = get_weight_axis(font)
    if not weight_axis:
        return font

    target_default = float(target_default)
    axis_min = float(weight_axis.minValue)
    axis_max = float(weight_axis.maxValue)
    old_default = weight_axis.defaultValue
    print(f"Changing default from {old_default} to {target_default:g}")

    if not axis_min <= target_default <= axis_max:
        raise ValueError(
            f"Target default {target_default:g} is outside wght axis "
            f"{axis_min:g}..{axis_max:g}"
        )

    max_weight_font = instantiateVariableFont(
        font,
        {"wght": axis_max},
        inplace=False,
        optimize=False,
        overlap=OverlapMode.KEEP_AND_DONT_SET_FLAGS,
        static=True,
    )
    adjusted_font = instantiateVariableFont(
        font,
        {"wght": (target_default, target_default, axis_max)},
        inplace=False,
        optimize=False,
    )

    rebuild_linear_gvar(adjusted_font, max_weight_font)
    update_instance_weight_values(adjusted_font)
    update_stat_default_weight(adjusted_font)

    for table_tag in ("HVAR", "avar"):
        if table_tag in adjusted_font:
            del adjusted_font[table_tag]

    weight_axis = get_weight_axis(adjusted_font)
    weight_axis.minValue = target_default
    weight_axis.defaultValue = target_default
    weight_axis.maxValue = axis_max

    return adjusted_font


def prepare_base_font(input_path: Path, target_default: float = 100) -> TTFont:
    """Adjust the default weight of base font to match target."""
    print(f"Preparing base font: {input_path}")
    font = TTFont(input_path)

    # Check current axis
    if "fvar" not in font:
        print("No fvar table found")
        return font

    weight_axis = next((ax for ax in font["fvar"].axes if ax.axisTag == "wght"), None)
    if not weight_axis:
        print("No wght axis found")
        return font

    print(
        f"Current wght axis: {weight_axis.minValue}/{weight_axis.defaultValue}/{weight_axis.maxValue}"
    )

    # Drop intermediate masters and shift default
    font = drop_intermediate_masters(font, target_default)
    weight_axis = get_weight_axis(font)

    print(
        f"Adjusted wght axis: {weight_axis.minValue}/{weight_axis.defaultValue}/{weight_axis.maxValue}\n"
    )

    return font


def merge_fonts(base: TTFont, extra: TTFont, output_path: Path) -> None:
    """Merge two variable fonts."""
    # Validate
    if base["head"].unitsPerEm != extra["head"].unitsPerEm:
        raise ValueError(
            f"UPEM mismatch: {base['head'].unitsPerEm} != {extra['head'].unitsPerEm}"
        )

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
            base_axis = get_weight_axis(base)

        print(
            f"Base axis after: wght {base_axis.minValue}/{base_axis.defaultValue}/{base_axis.maxValue}"
        )

    # Find glyphs to add
    base_glyphs = set(base.getGlyphOrder())
    extra_glyphs_to_add = [g for g in extra.getGlyphOrder() if g not in base_glyphs]

    print(f"Base glyphs: {len(base_glyphs)}")
    print(f"Extra glyphs to add: {len(extra_glyphs_to_add)}")

    # Merge glyph data
    base_glyf = base["glyf"]
    extra_glyf = extra["glyf"]
    base_hmtx = base["hmtx"]
    extra_hmtx = extra["hmtx"]
    base_gvar = base.get("gvar")
    extra_gvar = extra.get("gvar")

    for glyph_name in extra_glyphs_to_add:
        base_glyf.glyphs[glyph_name] = deepcopy(extra_glyf.glyphs[glyph_name])
        base_hmtx.metrics[glyph_name] = extra_hmtx.metrics[glyph_name]
        if base_gvar and extra_gvar:
            base_gvar.variations[glyph_name] = deepcopy(
                extra_gvar.variations.get(glyph_name, [])
            )

    # Update glyph order
    base.setGlyphOrder(list(base.getGlyphOrder()) + extra_glyphs_to_add)
    base["maxp"].numGlyphs = len(base.getGlyphOrder())

    # Merge cmap
    base_cmap_entries = {}
    for table in base["cmap"].tables:
        if table.isUnicode():
            base_cmap_entries.update(table.cmap)

    extra_cmap_entries = {}
    for table in extra["cmap"].tables:
        if table.isUnicode():
            extra_cmap_entries.update(table.cmap)

    new_mappings = {
        cp: glyph
        for cp, glyph in extra_cmap_entries.items()
        if glyph in extra_glyphs_to_add and cp not in base_cmap_entries
    }

    for table in base["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(new_mappings)

    print(f"Added {len(new_mappings)} new Unicode mappings")

    # Recalculate
    base["hhea"].numberOfHMetrics = len(base["hmtx"].metrics)
    base["hhea"].recalc(base)
    if "OS/2" in base:
        base["OS/2"].recalcAvgCharWidth(base)
        base["OS/2"].recalcUnicodeRanges(base)
        base["OS/2"].recalcCodePageRanges(base)

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(output_path)
    print(f"Saved: {output_path}")
    print(f"Total glyphs: {len(base.getGlyphOrder())}")


if __name__ == "__main__":
    # Prepare base font with adjusted default weight and merge
    base = prepare_base_font(
        Path("fonts/Variable/MapleMono[wght].ttf"), target_default=100
    )
    merge_fonts(
        base,
        TTFont("source/cn/WenYuanRoundedSCVF-MapleCN.ttf"),
        Path("fonts/MapleMono-CN-VF.ttf"),
    )

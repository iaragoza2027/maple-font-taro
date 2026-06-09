#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.instancer import instantiateVariableFont


FontInput = str | Path | TTFont
GlyphCoordinates = Any
GlyphEndpoint = tuple[GlyphCoordinates, GlyphCoordinates]


def merge_vf(base_font: FontInput, extra_font: FontInput) -> tuple[TTFont, list[str], int]:
    base = _load_font(base_font)
    extra = _load_font(extra_font)

    _validate_merge_inputs(base, extra)
    added_glyphs = _merge_glyph_tables(base, extra)
    added_codepoints = _merge_cmap(base, extra, set(added_glyphs))
    _recalculate_font(base)

    return base, added_glyphs, added_codepoints


def weight_axis(font: TTFont):
    if "fvar" not in font:
        return None
    return next((axis for axis in font["fvar"].axes if axis.axisTag == "wght"), None)


def rebuild_weight_masters(
    font: TTFont,
    default_master: TTFont,
    max_master: TTFont | None = None,
    axis_tag: str = "wght",
) -> None:
    """Replace weight masters with a sampled default and one linear max delta."""
    _require_tables(font, ("glyf", "hmtx", "gvar"))

    _replace_gvar_with_linear_axis(
        font,
        (
            (
                glyph_name,
                _glyph_coordinates(default_master, glyph_name),
                (
                    _glyph_coordinates(max_master, glyph_name)
                    if max_master is not None
                    else _interpolated_coordinates(font, glyph_name, axis_tag, 1.0)
                ),
            )
            for glyph_name in font.getGlyphOrder()
        ),
        axis_tag,
    )
    _drop_tables(font, ("HVAR", "MVAR"))


def normalize_weight_axis(
    font: TTFont,
    axis_name_id: int,
    axis_name: str,
    instance_weights: list[float],
    instances: list[tuple[int, str]],
    min_value: float = 100,
    default_value: float = 100,
    max_value: float = 800,
) -> None:
    if len(instance_weights) != len(instances):
        raise ValueError(
            "Instance weights and instance names must have the same length: "
            f"{len(instance_weights)} != {len(instances)}"
        )

    _require_tables(font, ("fvar", "name"))
    axis = _require_weight_axis(font)
    font["fvar"].axes = [axis]

    axis.minValue = float(min_value)
    axis.defaultValue = float(default_value)
    axis.maxValue = float(max_value)
    axis.flags = 0
    axis.axisNameID = axis_name_id
    _replace_name_record(font, axis_name_id, axis_name)

    original_instances = _roman_instances(font)
    original_names = _instance_names(font, original_instances)
    new_instances = []

    for instance_weight, (name_id, name) in zip(instance_weights, instances):
        instance = _find_instance_by_name(original_instances, original_names, name)
        instance.coordinates = {"wght": float(instance_weight)}
        instance.subfamilyNameID = name_id
        instance.postscriptNameID = 0xFFFF
        _replace_name_record(font, name_id, name)
        new_instances.append(instance)

    font["fvar"].instances = new_instances
    _drop_tables(font, ("avar",))


def change_default_master(
    font: TTFont,
    target_default: float,
    instance_weights: dict[str, float] | None = None,
    default_style: str = "Regular",
) -> TTFont:
    """Move the default master to target_default and keep one linear max delta."""
    _require_tables(font, ("fvar", "gvar"))
    axis = _require_weight_axis(font)

    target_default = float(target_default)
    axis_min = float(axis.minValue)
    axis_max = float(axis.maxValue)
    if not axis_min <= target_default <= axis_max:
        raise ValueError(
            f"Target default {target_default:g} is outside wght axis "
            f"{axis_min:g}..{axis_max:g}"
        )

    adjusted_font = instantiateVariableFont(
        font,
        {"wght": (target_default, target_default, axis_max)},
        inplace=False,
        optimize=False,
    )

    _replace_gvar_with_linear_axis(
        adjusted_font,
        (
            (
                glyph_name,
                _glyph_coordinates(adjusted_font, glyph_name),
                _interpolated_coordinates(adjusted_font, glyph_name, "wght", 1.0),
            )
            for glyph_name in adjusted_font.getGlyphOrder()
        ),
    )

    if instance_weights:
        _remap_instance_values(adjusted_font, instance_weights)
    _set_stat_default_value(adjusted_font, default_style)
    _drop_tables(adjusted_font, ("HVAR", "avar"))

    adjusted_axis = _require_weight_axis(adjusted_font)
    adjusted_axis.minValue = target_default
    adjusted_axis.defaultValue = target_default
    adjusted_axis.maxValue = axis_max

    return adjusted_font


def _load_font(font: FontInput) -> TTFont:
    if isinstance(font, TTFont):
        return font
    return TTFont(font)


def _require_tables(font: TTFont, table_tags: Iterable[str]) -> None:
    for table_tag in table_tags:
        if table_tag not in font:
            raise ValueError(f"Font is missing required table: {table_tag}")


def _drop_tables(font: TTFont, table_tags: Iterable[str]) -> None:
    for table_tag in table_tags:
        if table_tag in font:
            del font[table_tag]


def _require_weight_axis(font: TTFont):
    axis = weight_axis(font)
    if axis is None:
        raise ValueError("Font is missing required wght axis.")
    return axis


def _variable_axes(font: TTFont) -> list[tuple[str, float, float, float]]:
    _require_tables(font, ("fvar",))
    return [
        (axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue)
        for axis in font["fvar"].axes
    ]


def _unicode_cmap(font: TTFont) -> dict[int, str]:
    result: dict[int, str] = {}
    for table in font["cmap"].tables:
        if table.isUnicode():
            result.update(table.cmap)
    return result


def _validate_merge_inputs(base: TTFont, extra: TTFont) -> None:
    required_tables = ("glyf", "hmtx", "cmap", "fvar", "gvar")
    for font_role, font in (("Base", base), ("Extra", extra)):
        for table_tag in required_tables:
            if table_tag not in font:
                raise ValueError(f"{font_role} font is missing required table: {table_tag}")

    if base["head"].unitsPerEm != extra["head"].unitsPerEm:
        raise ValueError(
            "Cannot merge fonts with different UPEM values: "
            f"{base['head'].unitsPerEm} != {extra['head'].unitsPerEm}"
        )

    base_axes = _variable_axes(base)
    extra_axes = _variable_axes(extra)
    if base_axes != extra_axes:
        raise ValueError(
            "Cannot merge fonts with different variable axes: "
            f"{base_axes} != {extra_axes}"
        )


def _merge_cmap(base: TTFont, extra: TTFont, added_glyphs: set[str]) -> int:
    base_codepoints = set(_unicode_cmap(base))
    extra_entries = {
        codepoint: glyph_name
        for codepoint, glyph_name in _unicode_cmap(extra).items()
        if glyph_name in added_glyphs and codepoint not in base_codepoints
    }

    for table in base["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(extra_entries)

    return len(extra_entries)


def _merge_glyph_tables(base: TTFont, extra: TTFont) -> list[str]:
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


def _recalculate_font(font: TTFont) -> None:
    font["hhea"].numberOfHMetrics = len(font["hmtx"].metrics)
    font["hhea"].recalc(font)

    if "OS/2" in font:
        font["OS/2"].recalcAvgCharWidth(font)
        font["OS/2"].recalcUnicodeRanges(font)
        font["OS/2"].recalcCodePageRanges(font)


def _glyph_coordinates(font: TTFont, glyph_name: str) -> GlyphCoordinates:
    glyf = font["glyf"]
    h_metrics = font["hmtx"].metrics
    v_metrics = font["vmtx"].metrics if "vmtx" in font else None
    coordinates, _ = glyf._getCoordinatesAndControls(glyph_name, h_metrics, v_metrics)
    return coordinates


def _interpolated_coordinates(
    font: TTFont, glyph_name: str, axis_tag: str, normalized_position: float
) -> GlyphCoordinates:
    coordinates = _glyph_coordinates(font, glyph_name)
    for variation in font["gvar"].variations.get(glyph_name, []):
        support = variation.axes.get(axis_tag)
        if not support or variation.coordinates is None:
            continue

        scalar = _support_scalar_at_position(support, normalized_position)
        if scalar == 0:
            continue

        for index, delta in enumerate(variation.coordinates):
            if delta is None:
                continue
            dx, dy = delta
            x, y = coordinates[index]
            coordinates[index] = (x + dx * scalar, y + dy * scalar)

    return coordinates


def _support_scalar_at_position(support: tuple[float, ...], position: float) -> float:
    min_support, peak, max_support = _expand_support(support)

    if peak == 0:
        return 0.0
    if position == peak:
        return 1.0
    if position < peak:
        if position < min_support or peak == min_support:
            return 0.0
        return (position - min_support) / (peak - min_support)
    if position > max_support or max_support == peak:
        return 0.0
    return (max_support - position) / (max_support - peak)


def _expand_support(support: tuple[float, ...]) -> tuple[float, float, float]:
    if len(support) == 3:
        return support[0], support[1], support[2]
    peak = support[0]
    return peak, peak, peak


def _replace_gvar_with_linear_axis(
    font: TTFont,
    endpoints: Iterable[tuple[str, GlyphCoordinates, GlyphCoordinates]],
    axis_tag: str = "wght",
) -> None:
    _require_tables(font, ("glyf", "hmtx", "gvar"))

    glyf = font["glyf"]
    h_metrics = font["hmtx"].metrics
    v_metrics = font["vmtx"].metrics if "vmtx" in font else None
    variations = {}

    for glyph_name, default_coordinates, max_coordinates in endpoints:
        glyf._setCoordinates(glyph_name, default_coordinates, h_metrics, v_metrics)

        delta = _coordinate_delta(default_coordinates, max_coordinates, glyph_name)
        variations[glyph_name] = []
        if _has_delta(delta):
            variations[glyph_name].append(_linear_variation(axis_tag, delta))

    font["gvar"].variations = variations


def _coordinate_delta(
    from_coordinates: GlyphCoordinates,
    to_coordinates: GlyphCoordinates,
    glyph_name: str,
) -> list[tuple[int, int]]:
    if len(from_coordinates) != len(to_coordinates):
        raise ValueError(
            f"Point count mismatch for {glyph_name}: "
            f"{len(from_coordinates)} != {len(to_coordinates)}"
        )

    return [
        (int(round(to_x - from_x)), int(round(to_y - from_y)))
        for (from_x, from_y), (to_x, to_y) in zip(from_coordinates, to_coordinates)
    ]


def _has_delta(delta: list[tuple[int, int]]) -> bool:
    return any(dx or dy for dx, dy in delta)


def _linear_variation(axis_tag: str, delta: list[tuple[int, int]]) -> TupleVariation:
    return TupleVariation({axis_tag: (0.0, 1.0, 1.0)}, delta)


def _replace_name_record(font: TTFont, name_id: int, value: str) -> None:
    font["name"].names = [
        record for record in font["name"].names if record.nameID != name_id
    ]
    font["name"].setName(value, name_id, 3, 1, 0x409)


def _roman_instances(font: TTFont):
    return [
        instance
        for instance in font["fvar"].instances
        if instance.coordinates.get("ital", 0) == 0
    ]


def _instance_names(font: TTFont, instances) -> dict[int, str | None]:
    return {
        id(instance): font["name"].getDebugName(instance.subfamilyNameID)
        for instance in instances
    }


def _find_instance_by_name(instances, instance_names: dict[int, str | None], name: str):
    instance = next(
        (
            candidate
            for candidate in instances
            if instance_names[id(candidate)] == name
        ),
        None,
    )
    if instance is None:
        raise ValueError(f"Missing wght instance: {name}")
    return instance


def _remap_instance_values(
    font: TTFont, style_weights: dict[str, float], axis_tag: str = "wght"
) -> None:
    _require_tables(font, ("fvar", "name"))

    for instance in font["fvar"].instances:
        style_name = font["name"].getDebugName(instance.subfamilyNameID)
        weight_value = style_weights.get(style_name)
        if weight_value is not None:
            instance.coordinates[axis_tag] = float(weight_value)


def _set_stat_default_value(font: TTFont, default_style: str = "Regular") -> None:
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
        axis_value.Flags = 2 if value_name == default_style else 0

#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation


FontInput = str | Path | TTFont
GlyphCoordinates = Any


def merge_vf(base_font: FontInput, extra_font: FontInput) -> tuple[TTFont, list[str], int]:
    base = TTFont(base_font) if not isinstance(base_font, TTFont) else base_font
    extra = TTFont(extra_font) if not isinstance(extra_font, TTFont) else extra_font

    _validate_merge_inputs(base, extra)
    added_glyphs = _merge_glyph_tables(base, extra)
    added_codepoints = _merge_cmap(base, extra, set(added_glyphs))
    _recalculate_font(base)

    return base, added_glyphs, added_codepoints


def weight_axis(font: TTFont):
    if "fvar" not in font:
        return None
    return next((axis for axis in font["fvar"].axes if axis.axisTag == "wght"), None)


def get_unicode_cmap(font: TTFont) -> dict[int, str]:
    """Extract unicode cmap entries from font."""
    result: dict[int, str] = {}
    for table in font["cmap"].tables:
        if table.isUnicode():
            result.update(table.cmap)
    return result


def get_cmap_codepoints(font: TTFont) -> set[int]:
    """Extract all unicode codepoints from font."""
    codepoints: set[int] = set()
    for table in font["cmap"].tables:
        if table.isUnicode():
            codepoints.update(table.cmap)
    return codepoints


def rebuild_weight_masters_with_regular_default(
    font: TTFont,
    min_master: TTFont,
    regular_master: TTFont,
    max_master: TTFont | None = None,
    axis_tag: str = "wght",
) -> None:
    """Replace weight masters with Regular as default and min/max deltas."""
    if "glyf" not in font or "hmtx" not in font or "gvar" not in font:
        raise ValueError("Font is missing required table")

    glyf = font["glyf"]
    h_metrics = font["hmtx"].metrics  # type: ignore
    v_metrics = font["vmtx"].metrics if "vmtx" in font else None  # type: ignore
    variations = {}

    for glyph_name in font.getGlyphOrder():
        min_coords = _glyph_coordinates(min_master, glyph_name)
        reg_coords = _glyph_coordinates(regular_master, glyph_name)
        max_coords = (
            _glyph_coordinates(max_master, glyph_name)
            if max_master
            else _interpolated_coordinates(font, glyph_name, axis_tag, 1.0)
        )

        glyf._setCoordinates(glyph_name, reg_coords, h_metrics, v_metrics)  # type: ignore

        min_delta = _coordinate_delta(reg_coords, min_coords, glyph_name)
        max_delta = _coordinate_delta(reg_coords, max_coords, glyph_name)
        variations[glyph_name] = []
        if any(dx or dy for dx, dy in min_delta):
            variations[glyph_name].append(TupleVariation({axis_tag: (-1.0, -1.0, 0.0)}, min_delta))
        if any(dx or dy for dx, dy in max_delta):
            variations[glyph_name].append(TupleVariation({axis_tag: (0.0, 1.0, 1.0)}, max_delta))

    font["gvar"].variations = variations  # type: ignore

    for table in ("HVAR", "MVAR", "avar"):
        if table in font:
            del font[table]


def normalize_weight_axis(
    font: TTFont,
    axis_name_id: int,
    axis_name: str,
    instance_weights: list[float],
    instances: list[tuple[int, str]],
    default_value: float = 400,
) -> None:
    if len(instance_weights) != len(instances):
        raise ValueError(
            f"Instance weights and instance names must have the same length: "
            f"{len(instance_weights)} != {len(instances)}"
        )

    if "fvar" not in font or "name" not in font:
        raise ValueError("Font is missing required table")

    axis = weight_axis(font)
    if axis is None:
        raise ValueError("Font is missing required wght axis")

    font["fvar"].axes = [axis]
    axis.minValue = 100.0  # type: ignore
    axis.defaultValue = float(default_value)  # type: ignore
    axis.maxValue = 800.0  # type: ignore
    axis.flags = 0  # type: ignore
    axis.axisNameID = axis_name_id  # type: ignore

    font["name"].names = [r for r in font["name"].names if r.nameID != axis_name_id]  # type: ignore
    font["name"].setName(axis_name, axis_name_id, 3, 1, 0x409)  # type: ignore

    original_instances = [
        i for i in font["fvar"].instances if i.coordinates.get("ital", 0) == 0  # type: ignore
    ]
    original_names = {
        id(i): font["name"].getDebugName(i.subfamilyNameID) for i in original_instances  # type: ignore
    }
    new_instances = []

    for instance_weight, (name_id, name) in zip(instance_weights, instances):
        instance = next((c for c in original_instances if original_names[id(c)] == name), None)
        if instance is None:
            raise ValueError(f"Missing wght instance: {name}")
        instance.coordinates = {"wght": float(instance_weight)}  # type: ignore
        instance.subfamilyNameID = name_id  # type: ignore
        instance.postscriptNameID = 0xFFFF  # type: ignore
        font["name"].names = [r for r in font["name"].names if r.nameID != name_id]  # type: ignore
        font["name"].setName(name, name_id, 3, 1, 0x409)  # type: ignore
        new_instances.append(instance)

    font["fvar"].instances = new_instances  # type: ignore
    if "avar" in font:
        del font["avar"]


def _glyph_coordinates(font: TTFont, glyph_name: str) -> GlyphCoordinates:
    glyf = font["glyf"]
    h_metrics = font["hmtx"].metrics  # type: ignore
    v_metrics = font["vmtx"].metrics if "vmtx" in font else None  # type: ignore
    coordinates, _ = glyf._getCoordinatesAndControls(glyph_name, h_metrics, v_metrics)  # type: ignore
    return coordinates


def _interpolated_coordinates(
    font: TTFont, glyph_name: str, axis_tag: str, normalized_position: float
) -> GlyphCoordinates:
    coordinates = _glyph_coordinates(font, glyph_name)
    for variation in font["gvar"].variations.get(glyph_name, []):  # type: ignore
        support = variation.axes.get(axis_tag)
        if not support or variation.coordinates is None:
            continue

        min_s, peak, max_s = (support[0], support[1], support[2]) if len(support) == 3 else (support[0], support[0], support[0])
        if peak == 0:
            scalar = 0.0
        elif normalized_position == peak:
            scalar = 1.0
        elif normalized_position < peak:
            scalar = 0.0 if normalized_position < min_s or peak == min_s else (normalized_position - min_s) / (peak - min_s)
        else:
            scalar = 0.0 if normalized_position > max_s or max_s == peak else (max_s - normalized_position) / (max_s - peak)

        if scalar == 0:
            continue

        for index, delta in enumerate(variation.coordinates):
            if delta is None:
                continue
            dx, dy = delta
            x, y = coordinates[index]
            coordinates[index] = (x + dx * scalar, y + dy * scalar)

    return coordinates


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

    if "fvar" not in base:
        raise ValueError("Font is missing required table: fvar")

    base_axes = [
        (axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue)
        for axis in base["fvar"].axes
    ]
    extra_axes = [
        (axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue)
        for axis in extra["fvar"].axes
    ]
    if base_axes != extra_axes:
        raise ValueError(
            "Cannot merge fonts with different variable axes: "
            f"{base_axes} != {extra_axes}"
        )


def _merge_cmap(base: TTFont, extra: TTFont, added_glyphs: set[str]) -> int:
    base_cmap: dict[int, str] = {}
    for table in base["cmap"].tables:
        if table.isUnicode():
            base_cmap.update(table.cmap)

    extra_cmap: dict[int, str] = {}
    for table in extra["cmap"].tables:
        if table.isUnicode():
            extra_cmap.update(table.cmap)

    base_codepoints = set(base_cmap)
    extra_entries = {
        codepoint: glyph_name
        for codepoint, glyph_name in extra_cmap.items()
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

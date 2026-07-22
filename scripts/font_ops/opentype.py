from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from scripts.font_ops.fonttools import SubsetOptions, TTFont, newTable

from scripts.font_ops.names import default_weight_map, set_font_name
from scripts.utils.logging import logger


def add_ital_axis_to_stat(font: TTFont):
    """Add a fake ``ital`` axis to italic variable fonts."""
    logger.debug("Add italic STAT axis")
    from fontTools.ttLib.tables import otTables as ot

    name = font["name"]
    stat_table = font["STAT"].table
    name_id = name._findUnusedNameID()
    set_font_name(font, "Italic", name_id, True)

    axis_factory = cast(Callable[[], Any], getattr(ot, "AxisRecord"))
    axis = axis_factory()
    axis.AxisTag = "ital"
    axis.AxisOrdering = len(stat_table.DesignAxisRecord.Axis)
    axis.AxisNameID = name_id
    stat_table.DesignAxisRecord.Axis.append(axis)
    stat_table.DesignAxisCount += 1

    axis_value_factory = cast(Callable[[], Any], getattr(ot, "AxisValue"))
    axis_value = axis_value_factory()
    axis_value.AxisIndex = axis.AxisOrdering
    axis_value.Flags = 0
    axis_value.Format = 1
    axis_value.ValueNameID = name_id
    axis_value.Value = 1.0
    if stat_table.AxisValueArray is None:
        axis_value_array_factory = cast(
            Callable[[], Any], getattr(ot, "AxisValueArray")
        )
        stat_table.AxisValueArray = axis_value_array_factory()
        stat_table.AxisValueArray.AxisValue = []
        stat_table.AxisValueCount = 0
    stat_table.AxisValueArray.AxisValue.append(axis_value)
    stat_table.AxisValueCount += 1


def patch_instance(font: TTFont, all_weight_map: dict[str, int]):
    if all_weight_map == default_weight_map:
        logger.debug("Skip weight remapping because the mapping is unchanged")
        return
    if "fvar" not in font or "STAT" not in font:
        return
    if all_weight_map["thin"] != 100:
        raise Exception("Font weight of `thin` must be 100")
    if all_weight_map["extrabold"] != 800:
        raise Exception("Font weight of `extrabold` must be 800")

    value_to_name = {value: name for name, value in default_weight_map.items()}
    for instance in font["fvar"].instances:
        current_weight = int(instance.coordinates["wght"])
        weight_name = value_to_name.get(current_weight)
        if weight_name and weight_name in all_weight_map:
            instance.coordinates["wght"] = all_weight_map[weight_name]

    axes = font["fvar"].axes
    wght_index = next(
        (index for index, axis in enumerate(axes) if axis.axisTag == "wght"), None
    )
    if wght_index is None:
        return
    stat = font["STAT"].table
    if not stat.AxisValueArray:
        return

    def patch_single_value(obj: Any, attr: str) -> None:
        weight_name = value_to_name.get(int(getattr(obj, attr)))
        if weight_name and weight_name in all_weight_map:
            setattr(obj, attr, all_weight_map[weight_name])

    def patch_range_value(axis_value: Any) -> None:
        weight_name = value_to_name.get(int(axis_value.NominalValue))
        if weight_name and weight_name in all_weight_map:
            new_value = all_weight_map[weight_name]
            delta = new_value - axis_value.NominalValue
            axis_value.RangeMinValue += delta
            axis_value.RangeMaxValue += delta
            axis_value.NominalValue = new_value

    for axis_value in stat.AxisValueArray.AxisValue:
        if axis_value.Format != 4 and axis_value.AxisIndex != wght_index:
            continue
        if axis_value.Format == 1:
            patch_single_value(axis_value, "Value")
        elif axis_value.Format == 2:
            patch_range_value(axis_value)
        elif axis_value.Format == 3:
            patch_single_value(axis_value, "Value")
            patch_single_value(axis_value, "LinkedValue")
        elif axis_value.Format == 4:
            for record in axis_value.AxisValueRecord:
                if record.AxisIndex == wght_index:
                    patch_single_value(record, "Value")


def add_gasp(font: TTFont):
    logger.debug("Update GASP table")
    font["gasp"] = newTable("gasp")
    gasp = font.table("gasp")
    gasp.gaspRange = {65535: 15}


def remove_target_glyph(font: TTFont, glyph_name_suffix: str):
    from fontTools.subset import Options

    keep_glyphs = [
        glyph_name
        for glyph_name in font.getGlyphOrder()
        if not glyph_name.endswith(glyph_name_suffix)
    ]
    from scripts.font_ops.subset import subset_to_glyphs

    subset_to_glyphs(
        font,
        keep_glyphs,
        options=cast(SubsetOptions, Options(hinting=False)),
    )


DEFAULT_COMPAT_ALIASES: dict[int, int] = {
    0x2126: 0x03A9,
    0x212A: 0x004B,
    0x212B: 0x00C5,
}


def alias_codepoints(
    font: TTFont,
    extra_mapping: dict[int, int] | None = None,
) -> None:
    mapping = {**(extra_mapping or {}), **DEFAULT_COMPAT_ALIASES}

    dst_glyphs: dict[int, str] = {}
    for source, destination in mapping.items():
        glyph = next(
            (
                table.cmap[destination]
                for table in font["cmap"].tables
                if table.isUnicode() and destination in table.cmap
            ),
            None,
        )
        if glyph is not None:
            dst_glyphs[source] = glyph

    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(dst_glyphs)

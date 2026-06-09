#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from vf_utils import (
    merge_vf,
    normalize_weight_axis,
    rebuild_weight_masters_with_regular_default,
)


DEFAULT_INPUT = Path("source/cn/WenYuanRoundedSCVF.ttf")
DEFAULT_OUTPUT = Path("source/cn/WenYuanRounded-CN-VF.ttf")
DEFAULT_FEATURE_FONT = Path("source/MapleMono-CN-feature-VF.ttf")

BROAD_CJK_RANGES = (
    (0x2460, 0x24FF),
    (0x2E80, 0x2EFF),
    (0x2F00, 0x2FDF),
    (0x2FF0, 0x2FFF),
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

DROP_TABLES = ("BASE", "VVAR", "vhea", "vmtx")
KEEP_GPOS_FEATURES = {"kern"}
WIDTH_EXPANSION_OFFSET = 100
VERTICAL_EXPANSION_OFFSET = -25
WEIGHT_AXIS_NAME_ID = 256
WEIGHT_AXIS_NAME = "Weight"
OUTPUT_WEIGHT_MIN = 100
OUTPUT_WEIGHT_REGULAR = 400
WENYUAN_THIN_SOURCE_WEIGHT = 250
WENYUAN_REGULAR_SOURCE_WEIGHT = 450
MAPLE_HHEA_METRICS = {
    "ascent": 990,
    "descent": -270,
    "lineGap": 0,
    "caretSlopeRise": 1,
    "caretSlopeRun": 0,
    "caretOffset": 0,
}
MAPLE_OS2_METRICS = {
    "sTypoAscender": 990,
    "sTypoDescender": -270,
    "sTypoLineGap": 0,
    "usWinAscent": 1020,
    "usWinDescent": 300,
    "sxHeight": 550,
    "sCapHeight": 730,
    "usWidthClass": 5,
    "fsSelection": 64,
}
MAPLE_POST_METRICS = {
    "isFixedPitch": 1,
    "underlinePosition": -125,
    "underlineThickness": 50,
    "italicAngle": 0,
}
WEIGHT_MAPPING_POINTS = (
    (100, 100),
    (200, 210),
    (300, 320),
    (400, 400),
    (500, 490),
    (600, 570),
    (700, 680),
    (800, 800),
)
WEIGHT_INSTANCES = (
    (261, "Thin"),
    (262, "ExtraLight"),
    (263, "Light"),
    (259, "Regular"),
    (265, "Medium"),
    (266, "SemiBold"),
    (267, "Bold"),
    (268, "ExtraBold"),
)
STAT_WEIGHT_VALUES = (
    (261, "Thin", 100, 100, 155, 0),
    (262, "ExtraLight", 210, 155, 265, 0),
    (263, "Light", 320, 265, 360, 0),
    (259, "Regular", 400, 360, 445, 2),
    (265, "Medium", 490, 445, 530, 0),
    (266, "SemiBold", 570, 530, 625, 0),
    (267, "Bold", 680, 625, 740, 0),
    (268, "ExtraBold", 800, 740, 800, 0),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch WenYuanRoundedSCVF into a Maple CN-style variable font."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--keep-gpos-kern",
        action="store_true",
        help="Preserve GPOS kern when it remains valid after subsetting.",
    )
    parser.add_argument(
        "--no-width-normalize",
        action="store_true",
        help="Do not force kept glyph advance widths to Maple CN style.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing the output font.",
    )
    parser.add_argument(
        "--patched-output",
        type=Path,
        default=None,
        help="Optional debug path for the patched WenYuan font before feature merge.",
    )
    parser.add_argument(
        "--feature-font",
        type=Path,
        default=DEFAULT_FEATURE_FONT,
        help="Font whose glyphs should be excluded from the patched WenYuan output.",
    )
    return parser.parse_args()


def cmap_codepoints(font: TTFont) -> set[int]:
    codepoints: set[int] = set()
    for table in font["cmap"].tables:
        if table.isUnicode():
            codepoints.update(table.cmap)
    return codepoints


def cmap_items(font: TTFont) -> dict[int, str]:
    result: dict[int, str] = {}
    for table in font["cmap"].tables:
        if table.isUnicode():
            result.update(table.cmap)
    return result


def allowed_codepoints(source_codepoints: Iterable[int]) -> set[int]:
    allowed: set[int] = set()
    for start, end in BROAD_CJK_RANGES:
        allowed.update(cp for cp in source_codepoints if start <= cp <= end)
    return allowed


def set_windows_name(font: TTFont, name_id: int, value: str) -> None:
    font["name"].setName(value, name_id, 3, 1, 0x409)


def apply_horizontal_metrics(font: TTFont) -> None:
    hhea = font["hhea"]
    for attr, value in MAPLE_HHEA_METRICS.items():
        setattr(hhea, attr, value)

    os2 = font["OS/2"]
    for attr, value in MAPLE_OS2_METRICS.items():
        if hasattr(os2, attr):
            setattr(os2, attr, value)

    post = font["post"]
    for attr, value in MAPLE_POST_METRICS.items():
        setattr(post, attr, value)


def move_glyph_right(
    font: TTFont, glyph_name: str, horizontal_shift: int, vertical_shift
) -> None:
    if "glyf" not in font or horizontal_shift == 0:
        return

    glyf = font["glyf"]
    glyph = glyf[glyph_name]
    if glyph.isComposite():
        for component in glyph.components:
            if hasattr(component, "x"):
                component.x += horizontal_shift
            elif hasattr(component, "arg1") and not component.flags & 0x0002:
                component.arg1 += horizontal_shift
    elif getattr(glyph, "numberOfContours", 0) > 0:
        coordinates = glyph.coordinates
        if coordinates is None:
            coordinates, _, _ = glyph.getCoordinates(glyf)
            glyph.coordinates = coordinates
        coordinates.translate((horizontal_shift, vertical_shift))

    glyph.recalcBounds(glyf)


def normalize_widths(font: TTFont) -> None:
    cmap = cmap_items(font)
    zero_width_glyphs = {glyph for cp, glyph in cmap.items() if 0x0300 <= cp <= 0x036F}
    if "GlyphOrder" in font:
        zero_width_glyphs.add(".notdef")

    for glyph_name in font.getGlyphOrder():
        if glyph_name not in font["hmtx"].metrics:
            continue
        _, lsb = font["hmtx"].metrics[glyph_name]
        width = 0 if glyph_name in zero_width_glyphs else 1200
        if width:
            move_glyph_right(
                font, glyph_name, WIDTH_EXPANSION_OFFSET, VERTICAL_EXPANSION_OFFSET
            )
            lsb += WIDTH_EXPANSION_OFFSET
        font["hmtx"].metrics[glyph_name] = (width, lsb)

    if "hhea" in font:
        font["hhea"].advanceWidthMax = 1200

    if "HVAR" in font:
        del font["HVAR"]


def prune_stat(font: TTFont) -> None:
    if "STAT" not in font:
        return

    stat = font["STAT"].table
    if getattr(stat, "DesignAxisRecord", None):
        axes = [axis for axis in stat.DesignAxisRecord.Axis if axis.AxisTag == "wght"]
        for axis in axes:
            axis.AxisNameID = WEIGHT_AXIS_NAME_ID
            axis.AxisOrdering = 0
        stat.DesignAxisRecord.Axis = axes
        stat.DesignAxisRecord.AxisCount = len(axes)
        stat.DesignAxisCount = len(axes)

    if getattr(stat, "AxisValueArray", None):
        values = [
            value
            for value in stat.AxisValueArray.AxisValue
            if getattr(value, "Format", None) == 2
            and getattr(value, "AxisIndex", None) == 0
        ]
        values = values[: len(STAT_WEIGHT_VALUES)]
        for value, (name_id, name, nominal, range_min, range_max, flags) in zip(
            values, STAT_WEIGHT_VALUES
        ):
            value.ValueNameID = name_id
            value.NominalValue = float(nominal)
            value.RangeMinValue = float(range_min)
            value.RangeMaxValue = float(range_max)
            value.Flags = flags
            set_windows_name(font, name_id, name)
        stat.AxisValueArray.AxisValue = values
        stat.AxisValueCount = len(values)


def prune_layout_features(
    font: TTFont, table_tag: str, keep_features: set[str]
) -> None:
    if table_tag not in font:
        return

    layout = font[table_tag].table
    feature_list = getattr(layout, "FeatureList", None)
    script_list = getattr(layout, "ScriptList", None)
    lookup_list = getattr(layout, "LookupList", None)
    if not feature_list or not script_list or not lookup_list:
        return

    old_records = feature_list.FeatureRecord
    kept_old_indices = [
        index
        for index, record in enumerate(old_records)
        if record.FeatureTag in keep_features
    ]
    old_to_new_feature = {
        old_index: new_index for new_index, old_index in enumerate(kept_old_indices)
    }
    feature_list.FeatureRecord = [old_records[index] for index in kept_old_indices]
    feature_list.FeatureCount = len(feature_list.FeatureRecord)

    used_lookup_indices: set[int] = set()
    for record in feature_list.FeatureRecord:
        used_lookup_indices.update(record.Feature.LookupListIndex)

    old_to_new_lookup = {
        old_index: new_index
        for new_index, old_index in enumerate(sorted(used_lookup_indices))
    }
    lookup_list.Lookup = [
        lookup_list.Lookup[old_index] for old_index in sorted(used_lookup_indices)
    ]
    lookup_list.LookupCount = len(lookup_list.Lookup)

    for record in feature_list.FeatureRecord:
        record.Feature.LookupListIndex = [
            old_to_new_lookup[index] for index in record.Feature.LookupListIndex
        ]
        record.Feature.LookupCount = len(record.Feature.LookupListIndex)

    def prune_langsys(langsys) -> None:
        langsys.FeatureIndex = [
            old_to_new_feature[index]
            for index in langsys.FeatureIndex
            if index in old_to_new_feature
        ]
        langsys.FeatureCount = len(langsys.FeatureIndex)
        if langsys.ReqFeatureIndex not in (0xFFFF, 65535):
            langsys.ReqFeatureIndex = old_to_new_feature.get(
                langsys.ReqFeatureIndex, 0xFFFF
            )

    for script_record in script_list.ScriptRecord:
        script = script_record.Script
        if script.DefaultLangSys:
            prune_langsys(script.DefaultLangSys)
        for lang_record in script.LangSysRecord:
            prune_langsys(lang_record.LangSys)


def subset_font(font: TTFont, codepoints: set[int], keep_gpos_kern: bool) -> None:
    options = subset.Options()
    options.layout_features = sorted(KEEP_GPOS_FEATURES if keep_gpos_kern else set())
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.recalc_bounds = True
    options.recalc_timestamp = False
    options.notdef_outline = True
    options.recommended_glyphs = False

    sub = subset.Subsetter(options=options)
    sub.populate(unicodes=codepoints)
    sub.subset(font)


def keep_only_unicode_glyphs(
    font: TTFont, excluded_glyphs: set[str] | None = None
) -> set[str]:
    glyphs = {".notdef", *cmap_items(font).values()}
    removed_glyphs = (glyphs - {".notdef"}) & (excluded_glyphs or set())
    glyphs -= removed_glyphs

    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.recalc_bounds = True
    options.recalc_timestamp = False
    options.notdef_outline = True
    options.recommended_glyphs = False
    options.layout_features = []

    sub = subset.Subsetter(options=options)
    sub.populate(glyphs=glyphs)
    sub.subset(font)
    return removed_glyphs


def glyphs_from_font(path: Path) -> set[str]:
    return set(TTFont(path).getGlyphOrder()) - {".notdef"}


def recalculate(font: TTFont) -> None:
    if "OS/2" in font:
        font["OS/2"].recalcAvgCharWidth(font)
        font["OS/2"].recalcUnicodeRanges(font)
        font["OS/2"].recalcCodePageRanges(font)


def feature_tags(font: TTFont, table_tag: str) -> list[str]:
    if table_tag not in font:
        return []
    feature_list = getattr(font[table_tag].table, "FeatureList", None)
    if not feature_list:
        return []
    return sorted({record.FeatureTag for record in feature_list.FeatureRecord})


def print_summary(prefix: str, font: TTFont) -> None:
    axes = []
    if "fvar" in font:
        axes = [
            f"{axis.axisTag}:{axis.minValue:g}/{axis.defaultValue:g}/{axis.maxValue:g}"
            for axis in font["fvar"].axes
        ]
    print(f"{prefix} glyphs: {len(font.getGlyphOrder())}")
    print(f"{prefix} unicodes: {len(cmap_codepoints(font))}")
    print(f"{prefix} axes: {', '.join(axes) if axes else 'none'}")
    print(f"{prefix} GSUB features: {', '.join(feature_tags(font, 'GSUB')) or 'none'}")
    print(f"{prefix} GPOS features: {', '.join(feature_tags(font, 'GPOS')) or 'none'}")
    print(
        f"{prefix} dropped vertical tables present: {[tag for tag in DROP_TABLES if tag in font]}"
    )


def patch_font(args: argparse.Namespace) -> TTFont:
    source = TTFont(args.input)
    source_codepoints = cmap_codepoints(source)
    keep_codepoints = allowed_codepoints(source_codepoints)
    excluded_glyphs = glyphs_from_font(args.feature_font)

    print_summary("source", source)
    print(f"planned unicode keep: {len(keep_codepoints)}")
    print(f"planned unicode drop: {len(source_codepoints - keep_codepoints)}")
    print(f"planned feature font glyph exclusions: {len(excluded_glyphs)}")

    font = instantiateVariableFont(source, {"ital": 0}, inplace=False)
    min_master = instantiateVariableFont(
        source,
        {"ital": 0, "wght": WENYUAN_THIN_SOURCE_WEIGHT},
        inplace=False,
        optimize=False,
        static=True,
    )
    regular_master = instantiateVariableFont(
        source,
        {"ital": 0, "wght": WENYUAN_REGULAR_SOURCE_WEIGHT},
        inplace=False,
        optimize=False,
        static=True,
    )

    for table_tag in DROP_TABLES:
        if table_tag in font:
            del font[table_tag]

    rebuild_weight_masters_with_regular_default(font, min_master, regular_master)
    normalize_weight_axis(
        font,
        axis_name_id=WEIGHT_AXIS_NAME_ID,
        axis_name=WEIGHT_AXIS_NAME,
        instance_weights=[weight for _, weight in WEIGHT_MAPPING_POINTS],
        instances=list(WEIGHT_INSTANCES),
        default_value=OUTPUT_WEIGHT_REGULAR,
    )
    subset_font(font, keep_codepoints, args.keep_gpos_kern)
    if "GSUB" in font:
        del font["GSUB"]
    if args.keep_gpos_kern:
        prune_layout_features(font, "GPOS", KEEP_GPOS_FEATURES)
    elif "GPOS" in font:
        del font["GPOS"]

    removed_glyphs = keep_only_unicode_glyphs(font, excluded_glyphs)
    print(f"removed feature font glyphs: {len(removed_glyphs)}")
    prune_stat(font)
    apply_horizontal_metrics(font)
    if not args.no_width_normalize:
        normalize_widths(font)
    recalculate(font)

    print_summary("patched", font)
    return font


def main() -> None:
    args = parse_args()
    patched_font = patch_font(args)
    # feature_font = adjusted_feature_font(args.feature_font)
    feature_font = TTFont(args.feature_font)
    merged_font, added_glyphs, added_codepoints = merge_vf(feature_font, patched_font)
    normalize_weight_axis(
        merged_font,
        axis_name_id=WEIGHT_AXIS_NAME_ID,
        axis_name=WEIGHT_AXIS_NAME,
        instance_weights=[weight for _, weight in WEIGHT_MAPPING_POINTS],
        instances=list(WEIGHT_INSTANCES),
        default_value=OUTPUT_WEIGHT_REGULAR,
    )
    prune_stat(merged_font)

    print_summary("merged", merged_font)
    print(f"merged added glyphs: {len(added_glyphs)}")
    print(f"merged added unicodes: {added_codepoints}")

    if args.dry_run:
        print("dry-run: output not written")
        return

    if args.patched_output:
        args.patched_output.parent.mkdir(parents=True, exist_ok=True)
        patched_font.save(args.patched_output)
        print(f"saved patched font: {args.patched_output}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    merged_font.save(args.output)
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()

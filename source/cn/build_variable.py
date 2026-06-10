#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from copy import deepcopy
from pathlib import Path
from typing import Iterable

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from vf_utils import (
    merge_vf,
    normalize_weight_axis,
    rebuild_weight_masters_with_regular_default,
    weight_axis,
)


DEFAULT_WENYUAN_SOURCE = Path("source/cn/WenYuanRoundedSCVF.ttf")
DEFAULT_FEATURE_FONT = Path("source/MapleMono-CN-feature-VF.ttf")
DEFAULT_REGULAR_BASE = Path("fonts/Variable/MapleMono[wght].ttf")
DEFAULT_ITALIC_BASE = Path("fonts/Variable/MapleMono-Italic[wght].ttf")
DEFAULT_OUTPUT_DIR = Path("fonts/Variable")
DEFAULT_ITALIC_ANGLE = -10
DEFAULT_ITALIC_PIVOT_Y = 350

REGULAR_OUTPUT_NAME = "MapleMono-CN[wght].ttf"
ITALIC_OUTPUT_NAME = "MapleMono-CN-Italic[wght].ttf"

EXPECTED_WEIGHT_AXIS = (100.0, 400.0, 800.0)
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
WIDTH_EXPANSION_OFFSET = 100
VERTICAL_EXPANSION_OFFSET = -25
WEIGHT_AXIS_NAME_ID = 256
WEIGHT_AXIS_NAME = "Weight"
OUTPUT_WEIGHT_REGULAR = 400
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
        description="Build Maple Mono CN variable fonts from MapleMono and WenYuan."
    )
    parser.add_argument("--wenyuan-source", type=Path, default=DEFAULT_WENYUAN_SOURCE)
    parser.add_argument("--feature-font", type=Path, default=DEFAULT_FEATURE_FONT)
    parser.add_argument("--regular-base", type=Path, default=DEFAULT_REGULAR_BASE)
    parser.add_argument("--italic-base", type=Path, default=DEFAULT_ITALIC_BASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--angle",
        type=float,
        default=DEFAULT_ITALIC_ANGLE,
        help="Italic angle in degrees. Negative values lean right.",
    )
    parser.add_argument(
        "--italic-pivot-y",
        type=float,
        default=DEFAULT_ITALIC_PIVOT_Y,
        help="Y coordinate used as the fixed line for CJK italic shear.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and summarize fonts without writing output files.",
    )
    parser.add_argument(
        "--subset-output-dir",
        type=Path,
        default=None,
        help="Optional debug output directory for small verification subsets.",
    )
    parser.add_argument(
        "--subset-text",
        default="中",
        help="Text to keep in debug subsets.",
    )
    parser.add_argument(
        "--subset-only",
        action="store_true",
        help="Only build debug subsets for --subset-text.",
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


def replace_windows_name(font: TTFont, name_id: int, value: str) -> None:
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


def move_glyph(
    font: TTFont, glyph_name: str, horizontal_shift: int, vertical_shift: int
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
    zero_width_glyphs.add(".notdef")

    for glyph_name in font.getGlyphOrder():
        if glyph_name not in font["hmtx"].metrics:
            continue
        _, lsb = font["hmtx"].metrics[glyph_name]
        width = 0 if glyph_name in zero_width_glyphs else 1200
        if width:
            move_glyph(
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
            replace_windows_name(font, name_id, name)
        stat.AxisValueArray.AxisValue = values
        stat.AxisValueCount = len(values)


def subset_font(font: TTFont, codepoints: set[int]) -> None:
    ensure_gvar_entries(font)

    options = subset.Options()
    options.layout_features = []
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


def ensure_gvar_entries(font: TTFont) -> None:
    if "gvar" not in font:
        return

    variations = font["gvar"].variations
    for glyph_name in font.getGlyphOrder():
        if glyph_name not in variations:
            variations[glyph_name] = []


def keep_only_unicode_glyphs(font: TTFont, excluded_glyphs: set[str]) -> int:
    glyphs = {".notdef", *cmap_items(font).values()}
    removed_glyphs = (glyphs - {".notdef"}) & excluded_glyphs
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
    return len(removed_glyphs)


def glyphs_from_fonts(paths: Iterable[Path]) -> set[str]:
    glyphs: set[str] = set()
    for path in paths:
        font = TTFont(path)
        glyphs.update(font.getGlyphOrder())
        font.close()
    glyphs.discard(".notdef")
    return glyphs


def recalculate(font: TTFont) -> None:
    if "OS/2" in font:
        font["OS/2"].recalcAvgCharWidth(font)
        font["OS/2"].recalcUnicodeRanges(font)
        font["OS/2"].recalcCodePageRanges(font)
        font["OS/2"].xAvgCharWidth = 600


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


def require_weight_axis_values(
    font: TTFont, input_path: Path | None = None
) -> tuple[float, float, float]:
    axis = weight_axis(font)
    if not axis:
        suffix = f": {input_path}" if input_path else ""
        raise ValueError(f"Font is missing wght axis{suffix}")
    return (float(axis.minValue), float(axis.defaultValue), float(axis.maxValue))


def load_variable_font(input_path: Path) -> TTFont:
    print(f"Loading variable font: {input_path}")
    font = TTFont(input_path)

    if "fvar" not in font:
        raise ValueError(f"Font is missing fvar table: {input_path}")

    values = require_weight_axis_values(font, input_path)
    if values != EXPECTED_WEIGHT_AXIS:
        expected = "/".join(f"{value:g}" for value in EXPECTED_WEIGHT_AXIS)
        actual = "/".join(f"{value:g}" for value in values)
        raise ValueError(f"Expected wght axis {expected}, got {actual}: {input_path}")
    return font


def normalize_wght_axis(font: TTFont) -> None:
    normalize_weight_axis(
        font,
        axis_name_id=WEIGHT_AXIS_NAME_ID,
        axis_name=WEIGHT_AXIS_NAME,
        instance_weights=[weight for _, weight in WEIGHT_MAPPING_POINTS],
        instances=list(WEIGHT_INSTANCES),
        default_value=OUTPUT_WEIGHT_REGULAR,
    )


def subset_for_text(font: TTFont, text: str) -> TTFont:
    subset_font_copy = deepcopy(font)
    for table_tag in ("HVAR", "MVAR", "avar"):
        if table_tag in subset_font_copy:
            del subset_font_copy[table_tag]

    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.recalc_bounds = True
    options.recalc_timestamp = False
    options.notdef_outline = True
    options.recommended_glyphs = False
    options.layout_features = ["*"]

    sub = subset.Subsetter(options=options)
    sub.populate(text=text)
    sub.subset(subset_font_copy)
    recalculate(subset_font_copy)
    return subset_font_copy


def save_debug_subset(
    font: TTFont, output_dir: Path | None, filename: str, text: str
) -> None:
    if output_dir is None:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    subset_for_text(font, text).save(output_path)
    print(f"saved debug subset: {output_path}")


def patch_wenyuan(
    wenyuan_source: Path,
    excluded_glyphs: set[str],
    dry_run: bool,
    keep_codepoints: set[int] | None = None,
) -> TTFont:
    source = TTFont(wenyuan_source)
    source_codepoints = cmap_codepoints(source)
    is_debug_subset = keep_codepoints is not None
    if keep_codepoints is None:
        keep_codepoints = allowed_codepoints(source_codepoints)

    print_summary("source", source)
    print(f"planned unicode keep: {len(keep_codepoints)}")
    print(f"planned unicode drop: {len(source_codepoints - keep_codepoints)}")
    print(f"planned base/feature glyph exclusions: {len(excluded_glyphs)}")

    if is_debug_subset:
        subset_font(source, keep_codepoints)

    font = instantiateVariableFont(source, {"ital": 0}, inplace=False)
    source.close()

    for table_tag in DROP_TABLES:
        if table_tag in font:
            del font[table_tag]

    normalize_wght_axis(font)
    subset_font(font, keep_codepoints)
    if "GSUB" in font:
        del font["GSUB"]
    if "GPOS" in font:
        del font["GPOS"]

    removed_glyphs = keep_only_unicode_glyphs(font, excluded_glyphs)
    print(f"removed base/feature glyphs: {removed_glyphs}")
    prune_stat(font)
    apply_horizontal_metrics(font)
    normalize_widths(font)
    recalculate(font)

    print_summary("patched WenYuan", font)
    if dry_run:
        print("dry-run: patched WenYuan kept in memory only")
    return font


def subset_codepoints(text: str) -> set[int]:
    return {ord(char) for char in text}


def ot_round(value: float) -> int:
    return (
        int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))
    )


def calculate_skew(italic_angle_deg: float) -> float:
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


def skew_glyph(
    font: TTFont, glyph_name: str, skew_factor: float, pivot_y: float
) -> None:
    glyf_table = font["glyf"]
    glyph = glyf_table[glyph_name]
    transform = ((1, 0), (skew_factor, 1))
    # x_shift = ot_round(-pivot_y * skew_factor)

    if glyph.isComposite():
        coordinates, end_pts, flags = glyph.getCoordinates(glyf_table)
        glyph.coordinates = coordinates
        glyph.endPtsOfContours = end_pts
        glyph.flags = flags
        glyph.numberOfContours = len(end_pts)
        if hasattr(glyph, "components"):
            del glyph.components
    elif getattr(glyph, "numberOfContours", 0) > 0:
        if not hasattr(glyph, "coordinates") or glyph.coordinates is None:
            coordinates, _, _ = glyph.getCoordinates(glyf_table)
            glyph.coordinates = coordinates
        else:
            coordinates = glyph.coordinates
    else:
        glyph.recalcBounds(glyf_table)
        return

    glyph.coordinates.transform(transform)
    # glyph.coordinates.translate((x_shift, 0))

    glyph.recalcBounds(glyf_table)


def update_italic_metadata(font: TTFont, italic_angle_deg: float) -> None:
    if "post" in font:
        font["post"].italicAngle = italic_angle_deg

    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.fsSelection = (os2.fsSelection & ~0x40) | 0x01

    if "head" in font:
        font["head"].macStyle |= 0x02

    if "hhea" in font:
        hhea = font["hhea"]
        hhea.caretSlopeRise = 1000
        hhea.caretSlopeRun = ot_round(
            -math.tan(math.radians(italic_angle_deg)) * 1000
        )

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


def skew_glyphs(font: TTFont, italic_angle_deg: float, pivot_y: float) -> None:
    skew_factor = calculate_skew(italic_angle_deg)

    for glyph_name in font.getGlyphOrder():
        skew_glyph(font, glyph_name, skew_factor, pivot_y)


def italic_static_master(
    font: TTFont, weight: int, italic_angle_deg: float, pivot_y: float
) -> TTFont:
    master = instantiateVariableFont(
        font,
        {"wght": weight},
        inplace=False,
        optimize=False,
        static=True,
    )
    skew_glyphs(master, italic_angle_deg, pivot_y)
    update_italic_metadata(master, italic_angle_deg)
    recalculate(master)
    return master


def make_italic(
    font: TTFont, italic_angle_deg: float, pivot_y: float = DEFAULT_ITALIC_PIVOT_Y
) -> TTFont:
    italic_font = deepcopy(font)
    skew_factor = calculate_skew(italic_angle_deg)
    print(f"Italic angle: {italic_angle_deg:g} degrees")
    print(f"Skew factor: {skew_factor:.6f}")
    print(f"Italic pivot Y: {pivot_y:g}")
    print(f"Building italic masters from {len(font.getGlyphOrder())} CN extension glyphs...")

    min_master = italic_static_master(italic_font, 100, italic_angle_deg, pivot_y)
    regular_master = italic_static_master(italic_font, 400, italic_angle_deg, pivot_y)
    max_master = italic_static_master(italic_font, 800, italic_angle_deg, pivot_y)

    rebuild_weight_masters_with_regular_default(
        italic_font, min_master, regular_master, max_master
    )
    update_italic_metadata(italic_font, italic_angle_deg)
    recalculate(italic_font)
    return italic_font


def merge_fonts(base: TTFont, extra: TTFont, label: str) -> TTFont:
    base_axis = require_weight_axis_values(base)
    extra_axis = require_weight_axis_values(extra)
    print(f"{label} base axis: wght {base_axis[0]:g}/{base_axis[1]:g}/{base_axis[2]:g}")
    print(
        f"{label} extra axis: wght {extra_axis[0]:g}/{extra_axis[1]:g}/{extra_axis[2]:g}"
    )

    merged_font, added_glyphs, added_codepoints = merge_vf(base, extra)
    print(f"{label} added glyphs: {len(added_glyphs)}")
    print(f"{label} added unicodes: {added_codepoints}")
    print_summary(label, merged_font)
    return merged_font


def set_cn_names(font: TTFont, italic: bool) -> None:
    style = "Italic" if italic else "Regular"
    suffix = "-Italic" if italic else "-Regular"
    set_name(font, 1, "Maple Mono CN")
    set_name(font, 2, style)
    set_name(font, 4, f"Maple Mono CN {style}")
    set_name(font, 6, f"MapleMono-CN{suffix}")
    set_name(font, 16, "Maple Mono CN")
    set_name(font, 17, style)
    set_name(font, 25, "MapleMonoCN")


def build_cn_extension(
    feature_font_path: Path,
    wenyuan_source: Path,
    regular_base_path: Path,
    italic_base_path: Path,
    dry_run: bool,
    subset_output_dir: Path | None,
    subset_text: str,
    keep_codepoints: set[int] | None = None,
) -> TTFont:
    excluded_glyphs = glyphs_from_fonts(
        (feature_font_path, regular_base_path, italic_base_path)
    )
    patched_wenyuan = patch_wenyuan(
        wenyuan_source, excluded_glyphs, dry_run, keep_codepoints
    )
    save_debug_subset(
        patched_wenyuan,
        subset_output_dir,
        "patched-wenyuan-subset.ttf",
        subset_text,
    )
    feature_font = load_variable_font(feature_font_path)
    cn_extension = merge_fonts(feature_font, patched_wenyuan, "regular CN extension")
    normalize_wght_axis(cn_extension)
    prune_stat(cn_extension)
    return cn_extension


def build_debug_subsets(args: argparse.Namespace) -> None:
    if args.subset_output_dir is None:
        raise ValueError("--subset-only requires --subset-output-dir")

    regular_base = load_variable_font(args.regular_base)
    italic_base = load_variable_font(args.italic_base)
    cn_extension = build_cn_extension(
        args.feature_font,
        args.wenyuan_source,
        args.regular_base,
        args.italic_base,
        dry_run=True,
        subset_output_dir=args.subset_output_dir,
        subset_text=args.subset_text,
        keep_codepoints=subset_codepoints(args.subset_text),
    )
    save_debug_subset(
        cn_extension,
        args.subset_output_dir,
        "cn-extension-subset.ttf",
        args.subset_text,
    )

    italic_cn_extension = make_italic(cn_extension, args.angle, args.italic_pivot_y)
    save_debug_subset(
        italic_cn_extension,
        args.subset_output_dir,
        "cn-extension-italic-subset.ttf",
        args.subset_text,
    )

    regular_font = merge_fonts(regular_base, cn_extension, "regular final subset")
    italic_font = merge_fonts(italic_base, italic_cn_extension, "italic final subset")
    set_cn_names(regular_font, italic=False)
    set_cn_names(italic_font, italic=True)
    save_debug_subset(
        regular_font,
        args.subset_output_dir,
        "MapleMono-CN-subset.ttf",
        args.subset_text,
    )
    save_debug_subset(
        italic_font,
        args.subset_output_dir,
        "MapleMono-CN-Italic-subset.ttf",
        args.subset_text,
    )


def save_font(font: TTFont, output_path: Path, dry_run: bool) -> None:
    recalculate(font)
    if dry_run:
        print(f"dry-run: would save {output_path}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(output_path)
    print(f"saved: {output_path}")


def build(args: argparse.Namespace) -> None:
    if args.subset_only:
        build_debug_subsets(args)
        return

    regular_output = args.output_dir / REGULAR_OUTPUT_NAME
    italic_output = args.output_dir / ITALIC_OUTPUT_NAME

    regular_base = load_variable_font(args.regular_base)
    italic_base = load_variable_font(args.italic_base)
    cn_extension = build_cn_extension(
        args.feature_font,
        args.wenyuan_source,
        args.regular_base,
        args.italic_base,
        args.dry_run,
        args.subset_output_dir,
        args.subset_text,
    )
    cn_extension.save('./test.ttf')
    return
    save_debug_subset(
        cn_extension,
        args.subset_output_dir,
        "cn-extension-subset.ttf",
        args.subset_text,
    )
    italic_cn_extension = make_italic(cn_extension, args.angle, args.italic_pivot_y)
    save_debug_subset(
        italic_cn_extension,
        args.subset_output_dir,
        "cn-extension-italic-subset.ttf",
        args.subset_text,
    )

    regular_font = merge_fonts(regular_base, cn_extension, "regular final")
    italic_font = merge_fonts(italic_base, italic_cn_extension, "italic final")
    set_cn_names(regular_font, italic=False)
    set_cn_names(italic_font, italic=True)
    save_debug_subset(
        regular_font,
        args.subset_output_dir,
        "MapleMono-CN-subset.ttf",
        args.subset_text,
    )
    save_debug_subset(
        italic_font,
        args.subset_output_dir,
        "MapleMono-CN-Italic-subset.ttf",
        args.subset_text,
    )

    save_font(regular_font, regular_output, args.dry_run)
    save_font(italic_font, italic_output, args.dry_run)


def main() -> None:
    build(parse_args())


if __name__ == "__main__":
    main()

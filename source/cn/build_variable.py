#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont, otRound

from vf_utils import (
    get_cmap_codepoints,
    get_unicode_cmap,
    merge_vf,
    normalize_weight_axis,
    rebuild_weight_masters_with_regular_default,
    weight_axis,
)

# ============================================================================
# Configuration Constants
# ============================================================================

DEFAULT_WENYUAN_SOURCE = Path("source/cn/WenYuanRoundedSCVF.ttf")
DEFAULT_FEATURE_FONT = Path("source/MapleMono-CN-feature-VF.ttf")
DEFAULT_REGULAR_BASE = Path("fonts/Variable/MapleMono[wght].ttf")
DEFAULT_ITALIC_BASE = Path("fonts/Variable/MapleMono-Italic[wght].ttf")
DEFAULT_OUTPUT_DIR = Path("fonts/Variable")
DEFAULT_ITALIC_ANGLE = 10


@dataclass(frozen=True)
class BuildConfig:
    """Build configuration constants."""

    REGULAR_OUTPUT_NAME: str = "MapleMono-CN[wght].ttf"
    ITALIC_OUTPUT_NAME: str = "MapleMono-CN-Italic[wght].ttf"
    EXPECTED_WEIGHT_AXIS: tuple[float, float, float] = (100.0, 400.0, 800.0)
    DROP_TABLES: tuple[str, ...] = ("BASE", "VVAR", "vhea", "vmtx")
    WIDTH_EXPANSION_OFFSET: int = 100
    VERTICAL_EXPANSION_OFFSET: int = -25
    WEIGHT_AXIS_NAME_ID: int = 256
    WEIGHT_AXIS_NAME: str = "Weight"
    OUTPUT_WEIGHT_REGULAR: int = 400


# Create singleton instance
BUILD_CONFIG = BuildConfig()

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

# Backward compatibility - expose BUILD_CONFIG constants at module level
REGULAR_OUTPUT_NAME = BUILD_CONFIG.REGULAR_OUTPUT_NAME
ITALIC_OUTPUT_NAME = BUILD_CONFIG.ITALIC_OUTPUT_NAME
EXPECTED_WEIGHT_AXIS = BUILD_CONFIG.EXPECTED_WEIGHT_AXIS
DROP_TABLES = BUILD_CONFIG.DROP_TABLES
WIDTH_EXPANSION_OFFSET = BUILD_CONFIG.WIDTH_EXPANSION_OFFSET
VERTICAL_EXPANSION_OFFSET = BUILD_CONFIG.VERTICAL_EXPANSION_OFFSET
WEIGHT_AXIS_NAME_ID = BUILD_CONFIG.WEIGHT_AXIS_NAME_ID
WEIGHT_AXIS_NAME = BUILD_CONFIG.WEIGHT_AXIS_NAME
OUTPUT_WEIGHT_REGULAR = BUILD_CONFIG.OUTPUT_WEIGHT_REGULAR

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


# ============================================================================
# CLI & Configuration
# ============================================================================


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
        help="Right-leaning oblique angle in degrees.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and summarize fonts without writing output files.",
    )
    return parser.parse_args()


# ============================================================================
# Codepoint & Glyph Utilities
# ============================================================================


def allowed_codepoints(source_codepoints: Iterable[int]) -> set[int]:
    allowed: set[int] = set()
    for start, end in BROAD_CJK_RANGES:
        allowed.update(cp for cp in source_codepoints if start <= cp <= end)
    return allowed


# ============================================================================
# Naming & Metadata
# ============================================================================


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


# ============================================================================
# Metrics & Horizontal Adjustments
# ============================================================================


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
        coordinates.scale((1.02, 1.05))
        coordinates.translate((horizontal_shift, vertical_shift))

    glyph.recalcBounds(glyf)


def normalize_widths(font: TTFont) -> None:
    cmap = get_unicode_cmap(font)
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


# ============================================================================
# Font Subsetting & Pruning
# ============================================================================


def _make_subset_options() -> subset.Options:
    """Create standard subset options for font subsetting."""
    options = subset.Options()
    options.layout_features = []
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.recalc_bounds = True
    options.recalc_timestamp = False
    options.notdef_outline = True
    options.recommended_glyphs = False
    return options


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

    options = _make_subset_options()

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
    glyphs = {".notdef", *get_unicode_cmap(font).values()}
    removed_glyphs = (glyphs - {".notdef"}) & excluded_glyphs
    glyphs -= removed_glyphs

    options = _make_subset_options()

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


# ============================================================================
# Font Loading & Validation
# ============================================================================


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
    print(f"{prefix} unicodes: {len(get_cmap_codepoints(font))}")
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
    if values != BUILD_CONFIG.EXPECTED_WEIGHT_AXIS:
        expected = "/".join(f"{value:g}" for value in BUILD_CONFIG.EXPECTED_WEIGHT_AXIS)
        actual = "/".join(f"{value:g}" for value in values)
        raise ValueError(f"Expected wght axis {expected}, got {actual}: {input_path}")
    return font


# ============================================================================
# Weight Axis Normalization
# ============================================================================


def normalize_wght_axis(font: TTFont) -> None:
    normalize_weight_axis(
        font,
        axis_name_id=WEIGHT_AXIS_NAME_ID,
        axis_name=WEIGHT_AXIS_NAME,
        instance_weights=[weight for _, weight in WEIGHT_MAPPING_POINTS],
        instances=list(WEIGHT_INSTANCES),
        default_value=OUTPUT_WEIGHT_REGULAR,
    )


# ============================================================================
# Font Merging & Building
# ============================================================================


def _instantiate_wenyuan_static(source: TTFont, wght: int) -> TTFont:
    """Instantiate WenYuan to static ital=0 at specified weight."""
    font = instantiateVariableFont(source, {"ital": 0, "wght": wght}, inplace=False)
    for table_tag in DROP_TABLES:
        if table_tag in font:
            del font[table_tag]
    return font


def _subset_wenyuan_unicode(font: TTFont, keep_codepoints: set[int]) -> None:
    """Apply unicode subsetting and remove GSUB/GPOS features."""
    subset_font(font, keep_codepoints)
    if "GSUB" in font:
        del font["GSUB"]
    if "GPOS" in font:
        del font["GPOS"]


def _apply_wenyuan_finalization(font: TTFont) -> None:
    """Apply final metrics, pruning, and recalculation."""
    prune_stat(font)
    apply_horizontal_metrics(font)
    normalize_widths(font)
    recalculate(font)


def patch_wenyuan(
    wenyuan_source: Path,
    excluded_glyphs: set[str],
    dry_run: bool,
) -> TTFont:
    """
    Prepare WenYuan font for merging with Maple Mono base.

    Returns a font with:
    - CJK codepoints only (BROAD_CJK_RANGES)
    - Normalized weight axis (100/400/800)
    - No GSUB/GPOS features
    - Maple Mono metrics applied
    - All widths normalized to 1200 or 0
    """
    source = TTFont(wenyuan_source)
    source_codepoints = get_cmap_codepoints(source)
    keep_codepoints = allowed_codepoints(source_codepoints)

    print_summary("source", source)
    print(f"planned unicode keep: {len(keep_codepoints)}")
    print(f"planned unicode drop: {len(source_codepoints - keep_codepoints)}")
    print(f"planned base/feature glyph exclusions: {len(excluded_glyphs)}")

    # Stage 1: Instantiate three static masters at remapped source weights
    min_master = _instantiate_wenyuan_static(source, 200)    # source 200 → axis 100
    regular_master = _instantiate_wenyuan_static(source, 450) # source 450 → axis 400
    max_master = _instantiate_wenyuan_static(source, 800)    # source 800 → axis 800

    # Stage 2: Rebuild variable font from remapped masters
    # Keep source as base (it has gvar), instantiate only ital=0
    font = instantiateVariableFont(source, {"ital": 0}, inplace=False)
    source.close()
    for table_tag in DROP_TABLES:
        if table_tag in font:
            del font[table_tag]

    rebuild_weight_masters_with_regular_default(
        font, min_master, regular_master, max_master
    )
    normalize_wght_axis(font)

    # Stage 3: Apply subsetting
    _subset_wenyuan_unicode(font, keep_codepoints)

    # Stage 4: Remove excluded glyphs
    removed_glyphs = keep_only_unicode_glyphs(font, excluded_glyphs)
    print(f"removed base/feature glyphs: {removed_glyphs}")

    # Stage 5: Apply metrics and finalization
    _apply_wenyuan_finalization(font)

    print_summary("patched WenYuan", font)
    if dry_run:
        print("dry-run: patched WenYuan kept in memory only")
    return font


# ============================================================================
# Italic Generation
# ============================================================================


def calculate_skew(italic_angle_deg: float) -> float:
    return math.tan(math.radians(italic_angle_deg))


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


def component_matrix(component) -> tuple[float, float, float, float]:
    if not hasattr(component, "transform"):
        return (1, 0, 0, 1)
    return (
        component.transform[0][0],
        component.transform[0][1],
        component.transform[1][0],
        component.transform[1][1],
    )


def transform_component(
    component, transform: tuple[float, ...], update_position: bool = True
) -> None:
    xx1, xy1, yx1, yy1, dx1, dy1 = transform
    xx2, xy2, yx2, yy2 = component_matrix(component)
    x2 = getattr(component, "x", 0)
    y2 = getattr(component, "y", 0)

    xx = xx1 * xx2 + yx1 * xy2
    xy = xy1 * xx2 + yy1 * xy2
    yx = xx1 * yx2 + yx1 * yy2
    yy = xy1 * yx2 + yy1 * yy2
    if update_position:
        component.x = otRound(xx1 * x2 + yx1 * y2 + dx1)
        component.y = otRound(xy1 * x2 + yy1 * y2 + dy1)
    component.transform = [[xx, xy], [yx, yy]]


def skew_component(component, skew_factor: float) -> None:
    """Specialized skew transformation for components (no scale/rotation)."""
    transform = getattr(component, "transform", None)

    if transform is None:
        # Simple case: no existing transform, just add skew
        component.transform = [[1, 0], [skew_factor, 1]]
    else:
        # Existing transform: apply skew matrix multiplication
        # Skew matrix is [[1, 0], [s, 1]]
        # Result: [[xx, xy], [yx + s*xx, yy + s*xy]]
        xx, xy = transform[0]
        yx, yy = transform[1]
        component.transform = [[xx, xy], [yx + skew_factor * xx, yy + skew_factor * xy]]


def update_italic_metadata(font: TTFont, italic_angle_deg: float) -> None:
    if "post" in font:
        font["post"].italicAngle = -italic_angle_deg

    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.fsSelection = (os2.fsSelection & ~0x40) | 0x01

    if "head" in font:
        font["head"].macStyle |= 0x02

    if "hhea" in font:
        hhea = font["hhea"]
        hhea.caretSlopeRise = 1000
        hhea.caretSlopeRun = otRound(calculate_skew(italic_angle_deg) * 1000)

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


def skew_glyphs(font: TTFont, italic_angle_deg: float) -> None:
    skew_factor = calculate_skew(italic_angle_deg)
    glyf_table = font["glyf"]
    hmtx = font["hmtx"]
    original_metrics = hmtx.metrics
    composite_glyphs = []

    for glyph_name in font.getGlyphOrder():
        glyph = glyf_table[glyph_name]
        advance_width, _ = original_metrics.get(glyph_name, (0, 0))

        if getattr(glyph, "numberOfContours", 0) == 0:
            continue

        if glyph.isComposite():
            for component in glyph.components:
                skew_component(component, skew_factor)
            composite_glyphs.append(glyph_name)
        else:
            if not hasattr(glyph, "coordinates") or glyph.coordinates is None:
                coordinates, _, _ = glyph.getCoordinates(glyf_table)
                glyph.coordinates = coordinates

            glyph.coordinates.transform(((1, 0), (skew_factor, 1), (0, 0)))
            glyph.coordinates.translate((-otRound(skew_factor * advance_width / 2), 0))
            glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax = (
                glyph.coordinates.calcIntBounds()
            )
            hmtx[glyph_name] = (advance_width, glyph.xMin)

    # Batch recalculate composite bounds after all glyphs processed
    for glyph_name in composite_glyphs:
        glyph = glyf_table[glyph_name]
        glyph.recalcBounds(glyf_table)
        advance_width, _ = original_metrics.get(glyph_name, (0, 0))
        hmtx[glyph_name] = (advance_width, glyph.xMin)


def italic_static_master(font: TTFont, weight: int, italic_angle_deg: float) -> TTFont:
    master = instantiateVariableFont(
        font,
        {"wght": weight},
        inplace=False,
        optimize=False,
        static=True,
    )
    skew_glyphs(master, italic_angle_deg)
    update_italic_metadata(master, italic_angle_deg)
    recalculate(master)
    return master


def make_italic(font: TTFont, italic_angle_deg: float) -> TTFont:
    italic_font = deepcopy(font)
    skew_factor = calculate_skew(italic_angle_deg)
    print(f"Italic angle: {italic_angle_deg:g} degrees")
    print(f"Skew factor: {skew_factor:.6f}")
    print(
        f"Building italic masters from {len(font.getGlyphOrder())} CN extension glyphs..."
    )

    min_master = italic_static_master(italic_font, 100, italic_angle_deg)
    regular_master = italic_static_master(italic_font, 400, italic_angle_deg)
    max_master = italic_static_master(italic_font, 800, italic_angle_deg)

    rebuild_weight_masters_with_regular_default(
        italic_font, min_master, regular_master, max_master
    )
    update_italic_metadata(italic_font, italic_angle_deg)
    recalculate(italic_font)
    return italic_font


# ============================================================================
# Font Merging & Building (continued)
# ============================================================================


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
) -> TTFont:
    """
    Build Chinese extension variable font.

    Combines feature font with patched WenYuan source,
    excluding glyphs already present in base fonts.

    Returns:
        Variable font with normalized weight axis ready for merging.
    """
    excluded_glyphs = glyphs_from_fonts(
        (feature_font_path, regular_base_path, italic_base_path)
    )
    patched_wenyuan = patch_wenyuan(wenyuan_source, excluded_glyphs, dry_run)
    feature_font = load_variable_font(feature_font_path)
    cn_extension = merge_fonts(feature_font, patched_wenyuan, "regular CN extension")
    normalize_wght_axis(cn_extension)
    prune_stat(cn_extension)
    return cn_extension


def save_font(font: TTFont, output_path: Path, dry_run: bool) -> None:
    recalculate(font)
    if dry_run:
        print(f"dry-run: would save {output_path}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(output_path)
    print(f"saved: {output_path}")


def build(args: argparse.Namespace) -> None:
    regular_output = args.output_dir / BUILD_CONFIG.REGULAR_OUTPUT_NAME
    italic_output = args.output_dir / BUILD_CONFIG.ITALIC_OUTPUT_NAME

    regular_base = load_variable_font(args.regular_base)
    italic_base = load_variable_font(args.italic_base)
    cn_extension = build_cn_extension(
        args.feature_font,
        args.wenyuan_source,
        args.regular_base,
        args.italic_base,
        args.dry_run,
    )
    italic_cn_extension = make_italic(cn_extension, args.angle)

    regular_font = merge_fonts(regular_base, cn_extension, "regular final")
    italic_font = merge_fonts(italic_base, italic_cn_extension, "italic final")
    set_cn_names(regular_font, italic=False)
    set_cn_names(italic_font, italic=True)

    save_font(regular_font, regular_output, args.dry_run)
    save_font(italic_font, italic_output, args.dry_run)


# ============================================================================
# Entry Point
# ============================================================================


def main() -> None:
    build(parse_args())


if __name__ == "__main__":
    main()

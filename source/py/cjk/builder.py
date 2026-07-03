#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field, replace
from os import cpu_count, listdir, makedirs
from pathlib import Path
from typing import Any, Iterable, Literal

from fontTools import subset
from fontTools.misc.transform import Transform
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.subset import parse_unicodes
from fontTools.ttLib import TTFont, newTable
from fontTools.varLib.instancer import instantiateVariableFont

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from source.py.task._utils import archive
from source.py.cjk.vf import (
    _build_weight_variations,
    _glyph_coordinates,
    drop_font_tables,
    get_cmap_codepoints,
    get_unicode_cmap,
    load_font_eager,
    make_italic_master_file,
    make_italic_variable_font,
    merge_masters_into_vf,
    recalculate_font_metrics,
    update_italic_metadata,
    weight_axis,
)
from source.py.utils import get_directory_hash


OutlineMode = Literal["auto", "glyf", "cff2"]
UnicodePreset = Literal["cn", "jp", "tc", "kr"]
RESERVED_NAME_IDS = {1, 2, 4, 6, 16, 17, 25}


DEFAULT_MAPLE_HHEA_METRICS: dict[str, int] = {
    "ascent": 990,
    "descent": -270,
    "lineGap": 0,
    "caretSlopeRise": 1,
    "caretSlopeRun": 0,
    "caretOffset": 0,
}

DEFAULT_MAPLE_OS2_METRICS: dict[str, int] = {
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

DEFAULT_MAPLE_POST_METRICS: dict[str, int] = {
    "isFixedPitch": 1,
    "underlinePosition": -125,
    "underlineThickness": 50,
    "italicAngle": 0,
}

DEFAULT_CJK_RANGES: tuple[tuple[int, int], ...] = (
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

DEFAULT_CN_RANGES = DEFAULT_CJK_RANGES

DEFAULT_JP_RANGES: tuple[tuple[int, int], ...] = (
    (0x2460, 0x24FF),
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x31F0, 0x31FF),
    (0x3200, 0x33FF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F),
    (0xFF00, 0xFFEF),
)

DEFAULT_TC_RANGES: tuple[tuple[int, int], ...] = (
    (0x2460, 0x24FF),
    (0x2E80, 0x2EFF),
    (0x2F00, 0x2FDF),
    (0x2FF0, 0x2FFF),
    (0x3000, 0x303F),
    (0x3100, 0x312F),
    (0x31A0, 0x31EF),
    (0x3200, 0x33FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F),
    (0xFF00, 0xFFEF),
)

DEFAULT_KR_RANGES: tuple[tuple[int, int], ...] = (
    (0x2460, 0x24FF),
    (0x3000, 0x303F),
    (0x3130, 0x318F),
    (0x3200, 0x33FF),
    (0x4E00, 0x9FFF),
    (0xA960, 0xA97F),
    (0xAC00, 0xD7AF),
    (0xD7B0, 0xD7FF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F),
    (0xFF00, 0xFFEF),
)

@dataclass(frozen=True)
class CJKWeightInstance:
    """Named weight instance copied from the feature font."""

    name: str
    coordinate: float


CJK_MASTER_WEIGHTS = (100, 400, 800)
CJKMasterLocations = dict[int, dict[str, float]]


def ordered_master_locations(
    masters: CJKMasterLocations,
) -> tuple[tuple[int, dict[str, float]], tuple[int, dict[str, float]], tuple[int, dict[str, float]]]:
    """Return CJK master locations in output weight order."""
    missing = [weight for weight in CJK_MASTER_WEIGHTS if weight not in masters]
    if missing:
        raise ValueError(f"source.masters is missing output weights: {missing}")
    return tuple((weight, masters[weight]) for weight in CJK_MASTER_WEIGHTS)  # type: ignore[return-value]


@dataclass(frozen=True)
class CJKSourceConfig:
    """Input CJK variable font configuration."""

    path: Path
    masters: CJKMasterLocations
    outline_mode: OutlineMode = "auto"
    drop_tables: tuple[str, ...] = ()


@dataclass(frozen=True)
class CJKUnicodeConfig:
    """Unicode filtering configuration for the source font."""

    ranges: tuple[tuple[int, int], ...] = DEFAULT_CJK_RANGES
    filter_encoding: str | None = None
    exclude_feature_codepoints: bool = True


UNICODE_PRESETS: dict[UnicodePreset, CJKUnicodeConfig] = {
    "cn": CJKUnicodeConfig(ranges=DEFAULT_CN_RANGES),
    "jp": CJKUnicodeConfig(ranges=DEFAULT_JP_RANGES, filter_encoding="cp932"),
    "tc": CJKUnicodeConfig(ranges=DEFAULT_TC_RANGES),
    "kr": CJKUnicodeConfig(ranges=DEFAULT_KR_RANGES),
}


@dataclass(frozen=True)
class CJKTransformConfig:
    """Width and outline normalization applied to added CJK glyphs."""

    target_advance_width: int = 1200
    x_scale: float = 1.02
    y_scale: float = 1.05
    x_shift: int = 100
    y_shift: int = -25
    italic_angle: float = 10


@dataclass(frozen=True)
class CJKOutputConfig:
    """Output file layout."""

    dir: Path = Path("source/cjk")
    regular_variable: str = "MapleMono-CJK-VF.ttf"
    italic_variable: str = "MapleMono-CJK-Italic-VF.ttf"
    static_dir: str = "static"
    static_hash: str = "static.sha256"
    archive_name: str = "cjk-base-static.zip"


@dataclass(frozen=True)
class CJKNamingConfig:
    """Font family and file naming configuration."""

    family_name: str = "Maple Mono CJK"
    postscript_prefix: str = "MapleMonoCJK"
    static_file_prefix: str = "MapleMonoCJK"


@dataclass(frozen=True)
class CJKBuildConfig:
    """Complete CJK build configuration."""

    source: CJKSourceConfig
    feature_font_path: Path = Path("source/MapleMono-CN-feature-VF.ttf")
    output: CJKOutputConfig = field(default_factory=CJKOutputConfig)
    naming: CJKNamingConfig = field(default_factory=CJKNamingConfig)
    unicode: CJKUnicodeConfig = field(default_factory=CJKUnicodeConfig)
    transform: CJKTransformConfig = field(default_factory=CJKTransformConfig)
    temp_dir: Path = Path("source/cjk/temp")
    hhea_metrics: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_MAPLE_HHEA_METRICS)
    )
    os2_metrics: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_MAPLE_OS2_METRICS)
    )
    post_metrics: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_MAPLE_POST_METRICS)
    )
    allow_incompatible_glyphs: bool = False


def create_font_executor() -> Executor:
    """Create a bounded executor for expensive font instantiation work."""
    try:
        return ProcessPoolExecutor(max_workers=min(4, cpu_count() or 4))
    except (OSError, PermissionError):
        print("> Process pool unavailable; falling back to thread pool")
        return ThreadPoolExecutor(max_workers=4)


def remove_mac_name_records(font: TTFont) -> bool:
    """Remove legacy Mac name records from a font."""
    if "name" not in font:
        return False
    before = len(font["name"].names)
    font["name"].removeNames(platformID=1)  # type: ignore
    return len(font["name"].names) != before


def cleanup_static_font_file(font_path: str) -> None:
    """Apply final cleanup to a saved static font file."""
    font = load_font_eager(font_path)
    changed = drop_font_tables(font, ("kern", "GPOS"))
    changed = remove_mac_name_records(font) or changed
    if changed:
        font.save(font_path)
    font.close()


def instantiate_variable_font_file(
    input_path: str,
    output_path: str,
    axes: dict[str, float],
    static: bool = False,
    optimize: bool = True,
    drop_table_tags: Iterable[str] = (),
) -> None:
    """Instantiate a variable font from disk and save it to disk."""
    font = load_font_eager(input_path)
    print(f"Instantiating {input_path} with axes {axes}...")
    instance = instantiateVariableFont(
        font, axes, inplace=False, optimize=optimize, static=static
    )
    drop_font_tables(instance, drop_table_tags)
    instance.save(output_path)
    instance.close()
    font.close()


def instantiate_masters_from_vf(
    vf_path: Path,
    output_dir: Path,
    masters: CJKMasterLocations,
    process_pool: Executor,
    output_suffix: str = ".ttf",
    drop_table_tags: Iterable[str] = (),
) -> tuple[Path, Path, Path]:
    """Instantiate the configured static masters from a variable font."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    futures = []
    for output_weight, axes in ordered_master_locations(masters):
        output_path = output_dir / f"{output_weight}-master{output_suffix}"
        paths.append(output_path)
        futures.append(
            process_pool.submit(
                instantiate_variable_font_file,
                str(vf_path),
                str(output_path),
                axes,
                True,
                False,
                tuple(drop_table_tags),
            )
        )
    for future in futures:
        future.result()
    return tuple(paths)  # type: ignore


def subset_font(font: TTFont, codepoints: set[int]) -> None:
    """Subset font to specified Unicode codepoints."""
    if "gvar" in font:
        variations = font["gvar"].variations
        for glyph_name in font.getGlyphOrder():
            if glyph_name not in variations:
                variations[glyph_name] = []
    options = subset.Options()
    options.layout_features = []
    options.name_IDs = ["*"]  # type: ignore
    options.name_legacy = True
    options.name_languages = ["*"]  # type: ignore
    options.recalc_bounds = True
    options.recalc_timestamp = False
    options.notdef_outline = True
    options.recommended_glyphs = False
    sub = subset.Subsetter(options=options)
    sub.populate(unicodes=codepoints)
    sub.subset(font)


def get_allowed_codepoints(source_font: TTFont, config: CJKBuildConfig) -> set[int]:
    """Select source codepoints allowed by configured ranges and encoding."""
    source_codepoints = get_cmap_codepoints(source_font)
    allowed = {
        codepoint
        for codepoint in source_codepoints
        if any(start <= codepoint <= end for start, end in config.unicode.ranges)
    }
    if not config.unicode.filter_encoding:
        return allowed

    filtered: set[int] = set()
    for codepoint in allowed:
        try:
            chr(codepoint).encode(config.unicode.filter_encoding)
        except UnicodeEncodeError:
            continue
        filtered.add(codepoint)
    return filtered


def prepare_source_subset(
    source_path: Path,
    keep_codepoints: set[int],
    excluded_codepoints: set[int],
    config: CJKBuildConfig,
    out_path: Path,
) -> int:
    """Subset the CJK source to configured codepoints not already in the feature font."""
    font = load_font_eager(source_path)
    drop_font_tables(font, config.source.drop_tables)
    filtered_codepoints = (
        keep_codepoints - excluded_codepoints
        if config.unicode.exclude_feature_codepoints
        else keep_codepoints
    )
    removed = len(keep_codepoints) - len(filtered_codepoints)
    subset_font(font, filtered_codepoints)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(out_path)
    font.close()
    return removed


def detect_outline_mode(font: TTFont, requested: OutlineMode) -> Literal["glyf", "cff2"]:
    """Resolve an outline mode from config and font tables."""
    if requested == "glyf":
        if "glyf" not in font:
            raise ValueError("Requested glyf outlines, but source font has no glyf table")
        return "glyf"
    if requested == "cff2":
        if "CFF2" not in font:
            raise ValueError("Requested CFF2 outlines, but source font has no CFF2 table")
        return "cff2"
    if "glyf" in font:
        return "glyf"
    if "CFF2" in font:
        return "cff2"
    if "CFF " in font:
        raise ValueError(
            "CFF source fonts are static-only; this CJK builder requires a glyf or CFF2 variable font"
        )
    raise ValueError("Source font must contain either glyf or CFF2 outlines")


def apply_horizontal_metrics(font: TTFont, config: CJKBuildConfig) -> None:
    """Apply Maple Mono horizontal metrics to font."""
    for attr, value in config.hhea_metrics.items():
        setattr(font["hhea"], attr, value)
    for attr, value in config.os2_metrics.items():
        if hasattr(font["OS/2"], attr):
            setattr(font["OS/2"], attr, value)
    for attr, value in config.post_metrics.items():
        setattr(font["post"], attr, value)


def transform_glyph(
    font: TTFont,
    glyph_name: str,
    transform: CJKTransformConfig,
) -> None:
    """Apply configured scale and translation to one glyf glyph."""
    if "glyf" not in font:
        return
    glyf = font["glyf"]
    glyph = glyf[glyph_name]
    if glyph.isComposite():
        for component in glyph.components:
            if hasattr(component, "x"):
                component.x += transform.x_shift
            elif hasattr(component, "arg1") and not component.flags & 0x0002:
                component.arg1 += transform.x_shift
    elif getattr(glyph, "numberOfContours", 0) > 0:
        coordinates = glyph.coordinates
        if coordinates is None:
            coordinates, _, _ = glyph.getCoordinates(glyf)
            glyph.coordinates = coordinates
        coordinates.scale((transform.x_scale, transform.y_scale))
        coordinates.translate((transform.x_shift, transform.y_shift))
    glyph.recalcBounds(glyf)


def normalize_widths(
    font: TTFont,
    config: CJKBuildConfig,
    glyph_names: set[str] | None = None,
    protected_glyphs: set[str] | None = None,
) -> None:
    """Normalize added CJK glyph widths and apply configured transforms."""
    cmap = get_unicode_cmap(font)
    zero_width_glyphs = {glyph for cp, glyph in cmap.items() if 0x0300 <= cp <= 0x036F}
    zero_width_glyphs.add(".notdef")
    target_glyphs = (
        glyph_names if glyph_names is not None else set(font.getGlyphOrder())
    )
    if protected_glyphs:
        target_glyphs = target_glyphs - protected_glyphs
    for glyph_name in target_glyphs:
        if glyph_name not in font["hmtx"].metrics:
            continue
        _, lsb = font["hmtx"].metrics[glyph_name]
        width = 0 if glyph_name in zero_width_glyphs else config.transform.target_advance_width
        if width:
            transform_glyph(font, glyph_name, config.transform)
            lsb += config.transform.x_shift
        font["hmtx"].metrics[glyph_name] = (width, lsb)
    if "hhea" in font:
        font["hhea"].advanceWidthMax = config.transform.target_advance_width
    if "HVAR" in font:
        del font["HVAR"]


def transform_cff_glyphs(
    font: TTFont,
    transform: CJKTransformConfig,
    italic_angle: float | None = None,
    glyph_names: set[str] | None = None,
) -> None:
    """Apply static CFF outline transforms after CFF2 instantiation."""
    if "CFF " not in font or "hmtx" not in font:
        return

    top_dict = font["CFF "].cff.topDictIndex[0]
    char_strings = top_dict.CharStrings
    glyph_set = font.getGlyphSet()
    target_glyphs = glyph_names or set(font.getGlyphOrder())
    skew = math.tan(math.radians(italic_angle)) if italic_angle else 0

    for glyph_name in target_glyphs:
        if glyph_name not in char_strings or glyph_name not in glyph_set:
            continue
        advance_width, _ = font["hmtx"].metrics.get(glyph_name, (0, 0))
        matrix = Transform(
            transform.x_scale,
            0,
            skew,
            transform.y_scale,
            transform.x_shift - round(skew * advance_width / 2),
            transform.y_shift,
        )
        pen = T2CharStringPen(None, glyph_set, CFF2=False)
        glyph_set[glyph_name].draw(TransformPen(pen, matrix))
        old_char_string = char_strings[glyph_name]
        char_strings[glyph_name] = pen.getCharString(
            private=old_char_string.private,
            globalSubrs=old_char_string.globalSubrs,
        )


def convert_cff_static_to_glyf(font: TTFont) -> None:
    """Convert a static CFF font to TrueType glyf outlines."""
    if "CFF " not in font:
        return

    glyph_order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()
    glyf = newTable("glyf")
    glyf.glyphs = {}
    glyf.setGlyphOrder(glyph_order)

    for glyph_name in glyph_order:
        tt_pen = TTGlyphPen(glyph_set, outputImpliedClosingLine=True)
        cu2qu_pen = Cu2QuPen(tt_pen, max_err=1.0, reverse_direction=True)
        glyph_set[glyph_name].draw(cu2qu_pen)
        glyph = tt_pen.glyph()
        glyf.glyphs[glyph_name] = glyph
        if getattr(glyph, "numberOfContours", 0) > 0:
            glyph.recalcBounds(glyf)
        else:
            glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0

    font["glyf"] = glyf
    font["loca"] = newTable("loca")
    drop_font_tables(font, ("CFF ", "CFF2", "VORG", "VVAR", "vhea", "vmtx"))
    update_maxp_for_glyf(font)


def update_maxp_for_glyf(font: TTFont) -> None:
    """Populate TrueType maxp fields after CFF to glyf conversion."""
    font["maxp"].tableVersion = 0x00010000
    for attr, value in {
        "maxZones": 2,
        "maxTwilightPoints": 0,
        "maxStorage": 0,
        "maxFunctionDefs": 0,
        "maxInstructionDefs": 0,
        "maxStackElements": 0,
        "maxSizeOfInstructions": 0,
        "maxComponentElements": 0,
        "maxComponentDepth": 0,
    }.items():
        setattr(font["maxp"], attr, value)
    font["maxp"].numGlyphs = len(font.getGlyphOrder())
    font["maxp"].recalc(font)


def prune_stat(font: TTFont) -> None:
    """Prune STAT table to weight axis only."""
    if "STAT" not in font:
        return
    stat = font["STAT"].table
    if getattr(stat, "DesignAxisRecord", None):
        axes = [axis for axis in stat.DesignAxisRecord.Axis if axis.AxisTag == "wght"]
        stat.DesignAxisRecord.Axis = axes
        stat.DesignAxisRecord.AxisCount = len(axes)
        stat.DesignAxisCount = len(axes)


def recalculate_font(font: TTFont, config: CJKBuildConfig) -> None:
    """Recalculate common font metrics."""
    recalculate_font_metrics(font)
    if "OS/2" in font:
        font["OS/2"].xAvgCharWidth = config.transform.target_advance_width // 2


def load_feature_variable_font(input_path: Path, config: CJKBuildConfig) -> TTFont:
    """Load and validate the Maple feature variable font used as merge base."""
    print(f"Loading feature variable font: {input_path}")
    font = load_font_eager(input_path)
    if "fvar" not in font:
        raise ValueError(f"Font is missing fvar table: {input_path}")
    axis = weight_axis(font)
    if not axis:
        raise ValueError(f"Font is missing wght axis: {input_path}")
    return font


def update_variable_font_names(font: TTFont, subfamily: str, config: CJKBuildConfig) -> None:
    """Update variable font naming after merging CJK glyphs into the feature base."""
    family_name = config.naming.family_name
    full_name = f"{family_name} {subfamily}"
    postscript_name = f"{config.naming.postscript_prefix}-{subfamily.replace(' ', '')}"

    name_table = font["name"]
    move_fvar_instances_from_reserved_name_ids(font)
    for name_id in RESERVED_NAME_IDS:
        name_table.removeNames(nameID=name_id)

    name_table.setName(family_name, 1, 3, 1, 0x409)
    name_table.setName(subfamily, 2, 3, 1, 0x409)
    name_table.setName(full_name, 4, 3, 1, 0x409)
    name_table.setName(postscript_name, 6, 3, 1, 0x409)
    name_table.setName(family_name, 16, 3, 1, 0x409)
    name_table.setName(subfamily, 17, 3, 1, 0x409)
    name_table.setName(config.naming.postscript_prefix, 25, 3, 1, 0x409)


def move_fvar_instances_from_reserved_name_ids(font: TTFont) -> None:
    """Keep fvar instance names independent from family/style name records."""
    if "fvar" not in font or "name" not in font:
        return
    name_table = font["name"]
    next_name_id = max(record.nameID for record in name_table.names) + 1
    for instance in font["fvar"].instances:
        if instance.subfamilyNameID not in RESERVED_NAME_IDS:
            continue
        name = name_table.getDebugName(instance.subfamilyNameID)
        if not name:
            continue
        replacement = find_name_id(name_table, name, RESERVED_NAME_IDS)
        if replacement is None:
            replacement = next_name_id
            next_name_id += 1
            name_table.setName(name, replacement, 3, 1, 0x409)
        instance.subfamilyNameID = replacement


def find_name_id(name_table: Any, value: str, excluded: set[int]) -> int | None:
    """Find an existing name ID for a string outside a reserved ID set."""
    for record in name_table.names:
        if record.nameID in excluded:
            continue
        try:
            if record.toUnicode() == value:
                return int(record.nameID)
        except UnicodeDecodeError:
            continue
    return None


def merge_cjk_masters_into_vf(
    base: TTFont,
    min_master: TTFont,
    regular_master: TTFont,
    max_master: TTFont,
    allow_incompatible_glyphs: bool,
) -> tuple[list[str], int, int]:
    """Merge source masters into a VF, optionally keeping incompatible glyphs fixed."""
    if not allow_incompatible_glyphs:
        added, added_codepoints = merge_masters_into_vf(
            base, min_master, regular_master, max_master
        )
        return added, added_codepoints, 0

    base_glyph_order = base.getGlyphOrder()
    base_glyphs = set(base_glyph_order)
    glyphs_to_add = [
        glyph_name
        for glyph_name in regular_master.getGlyphOrder()
        if glyph_name not in base_glyphs
    ]

    base_glyf = base["glyf"]
    base_hmtx = base["hmtx"]
    base_gvar = base["gvar"]
    regular_glyf = regular_master["glyf"]
    regular_hmtx = regular_master["hmtx"]

    incompatible_glyphs = 0
    for glyph_name in glyphs_to_add:
        base_glyf.glyphs[glyph_name] = deepcopy(regular_glyf.glyphs[glyph_name])
        base_hmtx.metrics[glyph_name] = regular_hmtx.metrics[glyph_name]

        try:
            base_gvar.variations[glyph_name] = _build_weight_variations(
                _glyph_coordinates(regular_master, glyph_name),
                _glyph_coordinates(min_master, glyph_name),
                _glyph_coordinates(max_master, glyph_name),
                glyph_name,
            )
        except ValueError:
            base_gvar.variations[glyph_name] = []
            incompatible_glyphs += 1

    glyph_order = base_glyph_order + glyphs_to_add
    base.setGlyphOrder(glyph_order)
    base["maxp"].numGlyphs = len(glyph_order)
    added_codepoints = merge_cmap_entries(base, regular_master, set(glyphs_to_add))
    return glyphs_to_add, added_codepoints, incompatible_glyphs


def merge_cmap_entries(base: TTFont, extra: TTFont, added_glyphs: set[str]) -> int:
    """Merge Unicode cmap entries for added glyphs."""
    base_codepoints = set(get_unicode_cmap(base))
    extra_entries = {
        codepoint: glyph_name
        for codepoint, glyph_name in get_unicode_cmap(extra).items()
        if glyph_name in added_glyphs and codepoint not in base_codepoints
    }
    for table in base["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(extra_entries)
    return len(extra_entries)


def prepare_source_masters(
    subset_path: Path,
    config: CJKBuildConfig,
    process_pool: Executor,
) -> tuple[Path, Path, Path]:
    """Instantiate glyf source masters for the master-merge pipeline."""
    subset_font = load_font_eager(subset_path)
    try:
        outline_mode = detect_outline_mode(subset_font, config.source.outline_mode)
    finally:
        subset_font.close()

    if outline_mode == "cff2":
        raise ValueError(
            "CFF2 sources are built directly as CFF2 variable fonts; "
            "they are not converted to glyf masters."
        )

    return instantiate_masters_from_vf(
        subset_path,
        config.temp_dir / "source-masters",
        config.source.masters,
        process_pool,
        ".ttf",
    )


def finalize_variable_font(
    font: TTFont,
    added_glyphs: set[str],
    protected_glyphs: set[str],
    subfamily: str,
    config: CJKBuildConfig,
    is_italic: bool = False,
) -> None:
    """Apply final metrics, naming, axis, and table cleanup."""
    apply_horizontal_metrics(font, config)
    if is_italic:
        update_italic_metadata(font, config.transform.italic_angle)
    normalize_widths(font, config, glyph_names=added_glyphs, protected_glyphs=protected_glyphs)
    prune_stat(font)
    recalculate_font(font, config)
    update_variable_font_names(font, subfamily, config)


def source_weight_values(config: CJKBuildConfig) -> tuple[float, float, float]:
    """Read min/default/max source weight coordinates from configured masters."""
    values = []
    for output_weight, axes in ordered_master_locations(config.source.masters):
        if "wght" not in axes:
            raise ValueError(f"Source master {output_weight} is missing wght axis")
        values.append(float(axes["wght"]))
    min_weight, default_weight, max_weight = values
    if not min_weight <= default_weight <= max_weight:
        raise ValueError(
            "Source master wght values must be ordered 100 <= 400 <= 800"
        )
    return min_weight, default_weight, max_weight


def cff2_variable_axis_limits(config: CJKBuildConfig) -> dict[str, Any]:
    """Pin non-weight source axes while preserving source weight coordinates."""
    min_weight, default_weight, max_weight = source_weight_values(config)
    regular_axes = config.source.masters[400]
    limits = {
        axis: value
        for axis, value in regular_axes.items()
        if axis != "wght"
    }
    limits["wght"] = (min_weight, default_weight, max_weight)
    return limits


def map_weight_coordinate(
    coordinate: float,
    source_min: float,
    source_default: float,
    source_max: float,
    target_min: float,
    target_default: float,
    target_max: float,
) -> float:
    """Map a feature-font weight coordinate onto another weight axis."""
    if coordinate <= source_default:
        if source_default == source_min:
            return target_default
        ratio = (coordinate - source_min) / (source_default - source_min)
        return target_min + ratio * (target_default - target_min)
    if source_max == source_default:
        return target_default
    ratio = (coordinate - source_default) / (source_max - source_default)
    return target_default + ratio * (target_max - target_default)


def copy_name_records(source: TTFont, target: TTFont, name_ids: Iterable[int]) -> None:
    """Copy selected name records from one font to another."""
    if "name" not in source or "name" not in target:
        return
    name_ids = set(name_ids)
    target["name"].names = [
        record for record in target["name"].names if record.nameID not in name_ids
    ]
    target["name"].names.extend(
        deepcopy(record) for record in source["name"].names if record.nameID in name_ids
    )


def feature_weight_instances(feature_font: TTFont) -> tuple[CJKWeightInstance, ...]:
    """Read static weight instances from the Maple feature font."""
    if "fvar" not in feature_font:
        raise ValueError("Feature font is missing fvar table")
    instances: list[CJKWeightInstance] = []
    for instance in feature_font["fvar"].instances:
        if "wght" not in instance.coordinates:
            continue
        name = feature_font["name"].getDebugName(instance.subfamilyNameID)
        if not name:
            raise ValueError(
                f"Feature font is missing instance name ID {instance.subfamilyNameID}"
            )
        instances.append(CJKWeightInstance(name, float(instance.coordinates["wght"])))
    return tuple(sorted(instances, key=lambda item: item.coordinate))


def copy_feature_weight_metadata(target: TTFont, feature_font: TTFont) -> None:
    """Copy weight axis names and named instances from the feature font."""
    if "fvar" not in target or "fvar" not in feature_font:
        raise ValueError("Both target and feature fonts must contain fvar")
    target_axis = weight_axis(target)
    feature_axis = weight_axis(feature_font)
    if target_axis is None or feature_axis is None:
        raise ValueError("Both target and feature fonts must contain wght axis")

    target["fvar"].axes = [target_axis]
    target_axis.axisNameID = feature_axis.axisNameID
    target_axis.flags = feature_axis.flags

    target_ids = {feature_axis.axisNameID}
    for instance in feature_font["fvar"].instances:
        target_ids.add(instance.subfamilyNameID)
        if instance.postscriptNameID != 0xFFFF:
            target_ids.add(instance.postscriptNameID)
    copy_name_records(feature_font, target, target_ids)

    target_instances = []
    for instance in feature_font["fvar"].instances:
        cloned = deepcopy(instance)
        if "wght" in cloned.coordinates:
            cloned.coordinates = {
                "wght": map_weight_coordinate(
                    float(cloned.coordinates["wght"]),
                    float(feature_axis.minValue),
                    float(feature_axis.defaultValue),
                    float(feature_axis.maxValue),
                    float(target_axis.minValue),
                    float(target_axis.defaultValue),
                    float(target_axis.maxValue),
                )
            }
        target_instances.append(cloned)
    target["fvar"].instances = target_instances


def finalize_cff2_variable_font(
    font: TTFont,
    feature_font: TTFont,
    subfamily: str,
    config: CJKBuildConfig,
    is_italic: bool = False,
) -> None:
    """Apply metadata cleanup for a source-format CFF2 variable font."""
    apply_horizontal_metrics(font, config)
    if is_italic:
        update_italic_metadata(font, config.transform.italic_angle)
    normalize_widths(font, config)
    prune_stat(font)
    recalculate_font(font, config)
    copy_feature_weight_metadata(font, feature_font)
    prune_stat(font)
    recalculate_font(font, config)
    update_variable_font_names(font, subfamily, config)


def build_cff2_cjk_fonts(
    feature_font_path: Path,
    source_path: Path,
    config: CJKBuildConfig,
) -> tuple[TTFont, TTFont]:
    """Build CFF2 variable fonts without converting outlines to glyf first."""
    feature_font = load_feature_variable_font(feature_font_path, config)
    try:
        base_codepoints = get_cmap_codepoints(feature_font)

        source_font = load_font_eager(source_path)
        try:
            source_codepoints = get_cmap_codepoints(source_font)
            keep_codepoints = get_allowed_codepoints(source_font, config)
        finally:
            source_font.close()
        print(f"CJK source unicodes: {len(source_codepoints)}")
        print(f"CJK selected unicodes: {len(keep_codepoints)}")

        subset_path = config.temp_dir / "source-subset.otf"
        removed = prepare_source_subset(
            source_path, keep_codepoints, base_codepoints, config, subset_path
        )
        print(f"Removed base/feature unicodes from CJK subset: {removed}")

        subset_font_file = load_font_eager(subset_path)
        try:
            regular_font = instantiateVariableFont(
                subset_font_file,
                cff2_variable_axis_limits(config),
                inplace=False,
                optimize=False,
                static=False,
            )
        finally:
            subset_font_file.close()

        finalize_cff2_variable_font(regular_font, feature_font, "Regular", config)
        italic_font = deepcopy(regular_font)
        finalize_cff2_variable_font(
            italic_font,
            feature_font,
            "Italic",
            config,
            is_italic=True,
        )
    finally:
        feature_font.close()

    print(f"Regular CJK CFF2 font glyphs: {len(regular_font.getGlyphOrder())}")
    print(f"Regular CJK CFF2 font unicodes: {len(get_cmap_codepoints(regular_font))}")
    print(
        "CFF2 italic variable keeps source outlines; "
        "static italic fonts are slanted after instantiation."
    )
    return regular_font, italic_font


def build_regular_cjk_font(
    feature_font_path: Path,
    source_path: Path,
    config: CJKBuildConfig,
    process_pool: Executor,
) -> tuple[TTFont, tuple[Path, Path, Path]]:
    """Build the upright CJK base VF via the master-merge pipeline."""
    feature_font = load_feature_variable_font(feature_font_path, config)
    base_codepoints = get_cmap_codepoints(feature_font)
    protected_glyphs = set(get_unicode_cmap(feature_font).values())

    source_font = load_font_eager(source_path)
    try:
        source_codepoints = get_cmap_codepoints(source_font)
        keep_codepoints = get_allowed_codepoints(source_font, config)
    finally:
        source_font.close()
    print(f"CJK source unicodes: {len(source_codepoints)}")
    print(f"CJK selected unicodes: {len(keep_codepoints)}")

    subset_path = config.temp_dir / "source-subset.ttf"
    removed = prepare_source_subset(
        source_path, keep_codepoints, base_codepoints, config, subset_path
    )
    print(f"Removed base/feature unicodes from CJK subset: {removed}")

    master_paths = prepare_source_masters(subset_path, config, process_pool)
    min_master = load_font_eager(master_paths[0])
    regular_master = load_font_eager(master_paths[1])
    max_master = load_font_eager(master_paths[2])

    added, added_codepoints, incompatible_glyphs = merge_cjk_masters_into_vf(
        feature_font,
        min_master,
        regular_master,
        max_master,
        config.allow_incompatible_glyphs,
    )
    print(f"Regular CJK path added glyphs: {len(added)}")
    print(f"Regular CJK path added unicodes: {added_codepoints}")
    if incompatible_glyphs:
        print(f"Regular CJK path fixed-weight glyphs: {incompatible_glyphs}")

    finalize_variable_font(
        feature_font,
        set(added),
        protected_glyphs,
        "Regular",
        config,
    )

    print(f"Regular CJK base font glyphs: {len(feature_font.getGlyphOrder())}")
    print(f"Regular CJK base font unicodes: {len(get_cmap_codepoints(feature_font))}")

    min_master.close()
    regular_master.close()
    max_master.close()

    return feature_font, master_paths


def build_italic_cjk_font(
    feature_font_path: Path,
    source_master_paths: tuple[Path, Path, Path],
    config: CJKBuildConfig,
    process_pool: Executor,
) -> TTFont:
    """Build the italic CJK base VF by slanting feature and source masters."""
    feature_fresh = load_feature_variable_font(feature_font_path, config)
    protected_glyphs = set(get_unicode_cmap(feature_fresh).values())
    feature_axis = weight_axis(feature_fresh)
    if feature_axis is None:
        raise ValueError("Feature font is missing wght axis")
    feature_masters = {
        100: {"wght": float(feature_axis.minValue)},
        400: {"wght": float(feature_axis.defaultValue)},
        800: {"wght": float(feature_axis.maxValue)},
    }
    feature_master_paths = instantiate_masters_from_vf(
        feature_font_path,
        config.temp_dir / "feature-masters",
        feature_masters,
        process_pool,
    )
    italic_font = make_italic_variable_font(
        feature_fresh,
        config.transform.italic_angle,
        config.temp_dir,
        process_pool,
        feature_master_paths,
    )
    feature_fresh.close()

    italic_master_dir = config.temp_dir / "source-italic-masters"
    italic_master_dir.mkdir(parents=True, exist_ok=True)
    italic_futures = []
    italic_master_paths: list[Path] = []
    for index, name in enumerate(("min", "regular", "max")):
        out_path = italic_master_dir / f"source-italic-{name}-master.ttf"
        italic_master_paths.append(out_path)
        italic_futures.append(
            process_pool.submit(
                make_italic_master_file,
                str(source_master_paths[index]),
                str(out_path),
                config.transform.italic_angle,
            )
        )
    for future in italic_futures:
        future.result()

    slanted_min = load_font_eager(italic_master_paths[0])
    slanted_regular = load_font_eager(italic_master_paths[1])
    slanted_max = load_font_eager(italic_master_paths[2])

    added, added_codepoints, incompatible_glyphs = merge_cjk_masters_into_vf(
        italic_font,
        slanted_min,
        slanted_regular,
        slanted_max,
        config.allow_incompatible_glyphs,
    )
    print(f"Italic CJK path added glyphs: {len(added)}")
    print(f"Italic CJK path added unicodes: {added_codepoints}")
    if incompatible_glyphs:
        print(f"Italic CJK path fixed-weight glyphs: {incompatible_glyphs}")

    finalize_variable_font(
        italic_font,
        set(added),
        protected_glyphs,
        "Italic",
        config,
        is_italic=True,
    )

    slanted_min.close()
    slanted_regular.close()
    slanted_max.close()

    print(f"Italic CJK base font glyphs: {len(italic_font.getGlyphOrder())}")
    print(f"Italic CJK base font unicodes: {len(get_cmap_codepoints(italic_font))}")
    return italic_font


def instantiate_static_font_file(
    input_path: str,
    output_path: str,
    coordinate: float,
    name: str,
    is_italic: bool,
    config: CJKBuildConfig,
) -> None:
    """Instantiate one static CJK font and apply final naming cleanup."""
    print(f"Instantiating {name} {'Italic' if is_italic else ''}...")
    var_font = load_font_eager(input_path)
    drop_font_tables(var_font, ("STAT",))
    instance = instantiateVariableFont(
        var_font,
        {"wght": coordinate},
        inplace=False,
        static=True,
        downgradeCFF2="CFF2" in var_font,
    )

    subfamily = (f"{name} Italic" if is_italic else name).replace(
        "Regular Italic", "Italic"
    )

    if "CFF " in instance:
        transform_cff_glyphs(
            instance,
            config.transform,
            config.transform.italic_angle if is_italic else None,
        )
        normalize_widths(instance, config)
        if is_italic:
            update_italic_metadata(instance, config.transform.italic_angle)
        recalculate_font(instance, config)
        convert_cff_static_to_glyf(instance)
        recalculate_font(instance, config)

    instance["name"].setName(config.naming.family_name, 1, 3, 1, 0x409)
    instance["name"].setName(subfamily, 2, 3, 1, 0x409)
    instance["name"].setName(
        f"{config.naming.family_name} {subfamily}",
        4,
        3,
        1,
        0x409,
    )
    instance["name"].setName(
        f"{config.naming.postscript_prefix}-{subfamily.replace(' ', '')}",
        6,
        3,
        1,
        0x409,
    )

    drop_font_tables(instance, ("kern", "GPOS"))
    remove_mac_name_records(instance)
    instance.save(output_path)
    instance.close()
    var_font.close()


def mapped_static_instances(
    var_font_path: Path,
    feature_font: TTFont,
) -> tuple[CJKWeightInstance, ...]:
    """Map feature-font static instances onto a variable font's weight axis."""
    var_font = load_font_eager(var_font_path)
    try:
        var_axis = weight_axis(var_font)
        feature_axis = weight_axis(feature_font)
        if var_axis is None or feature_axis is None:
            raise ValueError("Both variable and feature fonts must contain wght axis")
        return tuple(
            CJKWeightInstance(
                instance.name,
                map_weight_coordinate(
                    instance.coordinate,
                    float(feature_axis.minValue),
                    float(feature_axis.defaultValue),
                    float(feature_axis.maxValue),
                    float(var_axis.minValue),
                    float(var_axis.defaultValue),
                    float(var_axis.maxValue),
                ),
            )
            for instance in feature_weight_instances(feature_font)
        )
    finally:
        var_font.close()


def instantiate_static_fonts(
    config: CJKBuildConfig,
    var_font_names: Iterable[str],
    process_pool: Executor,
) -> Path:
    """Instantiate all static fonts for the generated regular and italic VFs."""
    static_dir = config.output.dir / config.output.static_dir
    makedirs(static_dir, exist_ok=True)
    futures = []
    feature_font = load_feature_variable_font(config.feature_font_path, config)
    try:
        for font_name in var_font_names:
            is_italic = "Italic" in font_name
            input_path = config.output.dir / font_name
            for instance in mapped_static_instances(input_path, feature_font):
                output_name = (
                    f"{config.naming.static_file_prefix}-{instance.name}"
                    f"{'Italic' if is_italic else ''}.ttf"
                ).replace("RegularItalic", "Italic")
                output_path = static_dir / output_name
                futures.append(
                    process_pool.submit(
                        instantiate_static_font_file,
                        str(input_path),
                        str(output_path),
                        instance.coordinate,
                        instance.name,
                        is_italic,
                        config,
                    )
                )
    finally:
        feature_font.close()

    for future in futures:
        future.result()
    return static_dir


def build_cjk_fonts(config: CJKBuildConfig, vf_only: bool = False) -> None:
    """Build regular, italic, and optionally static CJK fonts."""
    print("> Building CJK fonts...")
    process_pool: Executor | None = None

    try:
        process_pool = create_font_executor()
        config.output.dir.mkdir(parents=True, exist_ok=True)

        regular_output = config.output.dir / config.output.regular_variable
        italic_output = config.output.dir / config.output.italic_variable
        source_font = load_font_eager(config.source.path)
        try:
            if "fvar" not in source_font:
                raise ValueError(
                    f"Source font must be variable: {config.source.path}"
                )
            outline_mode = detect_outline_mode(source_font, config.source.outline_mode)
        finally:
            source_font.close()

        if outline_mode == "cff2":
            regular_font, italic_font = build_cff2_cjk_fonts(
                config.feature_font_path,
                config.source.path,
                config,
            )
        else:
            regular_font, source_master_paths = build_regular_cjk_font(
                config.feature_font_path,
                config.source.path,
                config,
                process_pool,
            )
            italic_font = build_italic_cjk_font(
                config.feature_font_path,
                source_master_paths,
                config,
                process_pool,
            )

        print(f"> Save regular variable font to {regular_output}")
        regular_font.save(regular_output)
        regular_font.close()

        print(f"> Save italic variable font to {italic_output}")
        italic_font.save(italic_output)
        italic_font.close()

        if vf_only:
            print("> Skipping static font generation (--vf-only)")
            return

        print("> Instantiating static fonts...")
        static_dir = instantiate_static_fonts(
            config,
            (config.output.regular_variable, config.output.italic_variable),
            process_pool,
        )

        for filename in listdir(static_dir):
            font_path = static_dir / filename
            if font_path.is_file() and filename.endswith(".ttf"):
                cleanup_static_font_file(str(font_path))

        hash_path = config.output.dir / config.output.static_hash
        with open(hash_path, "w") as file:
            file.write(get_directory_hash(str(static_dir)))
            file.flush()
        print(f"> Update {hash_path}")

        archive(
            str(static_dir),
            str(config.output.dir / config.output.archive_name),
            lambda path: path.endswith(".ttf"),
        )
        print("> CJK rebuild complete.")
    finally:
        if process_pool:
            process_pool.shutdown(wait=True, cancel_futures=True)


def parse_codepoint(value: str | int) -> int:
    """Parse decimal or hex codepoint values."""
    if isinstance(value, int):
        return value
    return int(value, 16 if value.lower().startswith("0x") else 10)


def parse_range(value: str | list[Any] | tuple[Any, Any]) -> tuple[int, int]:
    """Parse a JSON Unicode range entry."""
    if isinstance(value, str):
        if not value.lower().startswith("0x") and "0x" not in value.lower():
            parsed = parse_unicodes(value)
            ranges = ranges_from_codepoints(parsed)
            if len(ranges) == 1:
                return ranges[0]
            raise ValueError(
                "JSON range entries must describe one range each; "
                f"use a list for multiple ranges: {value!r}"
            )
        delimiter = ".." if ".." in value else "-"
        if delimiter not in value:
            point = parse_codepoint(value)
            return point, point
        start, end = value.split(delimiter, 1)
        return parse_codepoint(start), parse_codepoint(end)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return parse_codepoint(value[0]), parse_codepoint(value[1])
    raise ValueError(f"Invalid Unicode range: {value!r}")


def ranges_from_codepoints(codepoints: Iterable[int]) -> tuple[tuple[int, int], ...]:
    """Compress codepoints into stable contiguous ranges."""
    ordered = sorted(set(codepoints))
    if not ordered:
        return ()

    ranges: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for codepoint in ordered[1:]:
        if codepoint == previous + 1:
            previous = codepoint
            continue
        ranges.append((start, previous))
        start = previous = codepoint
    ranges.append((start, previous))
    return tuple(ranges)


def validate_ranges(ranges: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """Validate parsed Unicode ranges."""
    result = tuple(ranges)
    for start, end in result:
        if start > end:
            raise ValueError(f"Invalid Unicode range order: {start:#x}-{end:#x}")
        if start < 0 or end > 0x10FFFF:
            raise ValueError(f"Unicode range out of bounds: {start:#x}-{end:#x}")
    return result


def parse_master_locations(value: Any) -> CJKMasterLocations:
    """Parse output-weight keyed source master locations from JSON."""
    if not isinstance(value, dict):
        raise ValueError(
            "source.masters must be an object keyed by output weights 100, 400, and 800"
        )
    masters: CJKMasterLocations = {}
    for raw_weight, raw_axes in value.items():
        try:
            output_weight = int(raw_weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid source master output weight: {raw_weight}") from exc
        if output_weight not in CJK_MASTER_WEIGHTS:
            raise ValueError(
                "source.masters keys must be exactly output weights 100, 400, and 800"
            )
        if not isinstance(raw_axes, dict):
            raise ValueError(f"source.masters.{output_weight} must be an object")
        axes = {str(axis): float(coordinate) for axis, coordinate in raw_axes.items()}
        if "wght" not in axes:
            raise ValueError(f"source.masters.{output_weight} must include wght")
        masters[output_weight] = axes
    ordered_master_locations(masters)
    return masters


def unicode_config_from_spec(
    spec: str,
    exclude_feature_codepoints: bool = True,
) -> CJKUnicodeConfig:
    """Resolve a named Unicode preset or pyftsubset-style unicode range."""
    if spec in UNICODE_PRESETS:
        preset = UNICODE_PRESETS[spec]
        return replace(
            preset,
            exclude_feature_codepoints=exclude_feature_codepoints,
        )

    ranges = validate_ranges(ranges_from_codepoints(parse_unicodes(spec)))
    if not ranges:
        raise ValueError(f"No Unicode codepoints parsed from: {spec}")
    return CJKUnicodeConfig(
        ranges=ranges,
        exclude_feature_codepoints=exclude_feature_codepoints,
    )


def apply_unicode_override(
    config: CJKBuildConfig,
    unicode_spec: str | None,
) -> CJKBuildConfig:
    """Override a build config's Unicode filter from CLI input."""
    if not unicode_spec:
        return config
    unicode_config = unicode_config_from_spec(
        unicode_spec,
        exclude_feature_codepoints=config.unicode.exclude_feature_codepoints,
    )
    return replace(config, unicode=unicode_config)


def parse_axis_assignment(value: str) -> tuple[str, float]:
    """Parse a CLI axis assignment like ROND=100."""
    if "=" not in value:
        raise ValueError(f"Axis assignment must use TAG=VALUE syntax: {value}")
    axis, raw_value = value.split("=", 1)
    axis = axis.strip()
    if not axis:
        raise ValueError(f"Axis tag is empty: {value}")
    return axis, float(raw_value)


def parse_axis_assignments(values: Iterable[str] | None) -> dict[str, float]:
    """Parse CLI axis assignments into a dictionary."""
    axes: dict[str, float] = {}
    for value in values or ():
        axis, coordinate = parse_axis_assignment(value)
        axes[axis] = coordinate
    return axes


def infer_weight_values(
    source_path: Path,
    wght_min: float | None = None,
    wght_regular: float | None = None,
    wght_max: float | None = None,
) -> tuple[float, float, float]:
    """Infer missing weight coordinates from a source variable font."""
    font = load_font_eager(source_path)
    try:
        if "fvar" not in font:
            raise ValueError(f"Source font must be variable: {source_path}")
        axis = weight_axis(font)
        if axis is None:
            raise ValueError(f"Source font is missing wght axis: {source_path}")
        return (
            float(axis.minValue if wght_min is None else wght_min),
            float(axis.defaultValue if wght_regular is None else wght_regular),
            float(axis.maxValue if wght_max is None else wght_max),
        )
    finally:
        font.close()


def build_master_locations(
    source_path: Path,
    fixed_axes: dict[str, float],
    wght_min: float | None = None,
    wght_regular: float | None = None,
    wght_max: float | None = None,
) -> CJKMasterLocations:
    """Build output-weight keyed master locations from source axis coordinates."""
    min_weight, regular_weight, max_weight = infer_weight_values(
        source_path,
        wght_min,
        wght_regular,
        wght_max,
    )
    if not min_weight <= regular_weight <= max_weight:
        raise ValueError("wght values must be ordered min <= regular <= max")

    def axes(weight: float) -> dict[str, float]:
        values = dict(fixed_axes)
        values["wght"] = weight
        return values

    return {
        100: axes(min_weight),
        400: axes(regular_weight),
        800: axes(max_weight),
    }


def resolve_cli_path(value: str | None) -> Path | None:
    """Resolve an optional CLI path relative to the current working directory."""
    if not value:
        return None
    return Path(value).expanduser()


def resolve_output_config(
    base: CJKOutputConfig,
    output_dir: str | None = None,
    regular_output: str | None = None,
    italic_output: str | None = None,
    static_dir: str | None = None,
    static_hash: str | None = None,
    archive_name: str | None = None,
) -> CJKOutputConfig:
    """Resolve CLI output overrides into the shared output directory model."""
    directory = Path(output_dir).expanduser() if output_dir else base.dir
    regular_name = base.regular_variable
    italic_name = base.italic_variable

    for raw_output, attr in (
        (regular_output, "regular"),
        (italic_output, "italic"),
    ):
        if not raw_output:
            continue
        output_path = Path(raw_output).expanduser()
        if output_path.parent != Path("."):
            if output_dir and output_path.parent != directory:
                raise ValueError(
                    f"{attr} output parent conflicts with --output-dir: {output_path}"
                )
            directory = output_path.parent
        if attr == "regular":
            regular_name = output_path.name
        else:
            italic_name = output_path.name

    return CJKOutputConfig(
        dir=directory,
        regular_variable=regular_name,
        italic_variable=italic_name,
        static_dir=static_dir or base.static_dir,
        static_hash=static_hash or base.static_hash,
        archive_name=archive_name or base.archive_name,
    )


def default_output_for_source(source_path: Path, outline_mode: OutlineMode) -> CJKOutputConfig:
    """Choose extension-safe default output names for a source font."""
    font = load_font_eager(source_path)
    try:
        resolved_mode = detect_outline_mode(font, outline_mode)
    finally:
        font.close()
    extension = "otf" if resolved_mode == "cff2" else "ttf"
    return CJKOutputConfig(
        regular_variable=f"MapleMono-CJK-VF.{extension}",
        italic_variable=f"MapleMono-CJK-Italic-VF.{extension}",
    )


def apply_cli_overrides(config: CJKBuildConfig, args: argparse.Namespace) -> CJKBuildConfig:
    """Apply direct CLI overrides on top of a JSON or default config."""
    source_path = resolve_cli_path(getattr(args, "source", None)) or config.source.path
    fixed_axes = parse_axis_assignments(getattr(args, "axis", None))
    has_master_override = fixed_axes or any(
        getattr(args, name, None) is not None
        for name in ("wght_min", "wght_regular", "wght_max")
    )
    masters = (
        build_master_locations(
            source_path,
            fixed_axes,
            getattr(args, "wght_min", None),
            getattr(args, "wght_regular", None),
            getattr(args, "wght_max", None),
        )
        if has_master_override
        else config.source.masters
    )
    source = CJKSourceConfig(
        path=source_path,
        masters=masters,
        outline_mode=getattr(args, "outline_mode", None) or config.source.outline_mode,
        drop_tables=tuple(getattr(args, "drop_table", None) or config.source.drop_tables),
    )

    output = resolve_output_config(
        config.output,
        getattr(args, "output_dir", None),
        getattr(args, "regular_output", None),
        getattr(args, "italic_output", None),
        getattr(args, "static_dir", None),
        getattr(args, "static_hash", None),
        getattr(args, "archive_name", None),
    )
    naming = CJKNamingConfig(
        family_name=getattr(args, "family_name", None) or config.naming.family_name,
        postscript_prefix=getattr(args, "postscript_prefix", None)
        or config.naming.postscript_prefix,
        static_file_prefix=getattr(args, "static_file_prefix", None)
        or config.naming.static_file_prefix,
    )
    unicode = config.unicode
    if getattr(args, "filter_encoding", None) is not None:
        unicode = replace(unicode, filter_encoding=args.filter_encoding)
    if getattr(args, "include_feature_codepoints", False):
        unicode = replace(unicode, exclude_feature_codepoints=False)

    transform = CJKTransformConfig(
        target_advance_width=getattr(args, "target_advance_width", None)
        or config.transform.target_advance_width,
        x_scale=getattr(args, "x_scale", None) or config.transform.x_scale,
        y_scale=getattr(args, "y_scale", None) or config.transform.y_scale,
        x_shift=getattr(args, "x_shift", None)
        if getattr(args, "x_shift", None) is not None
        else config.transform.x_shift,
        y_shift=getattr(args, "y_shift", None)
        if getattr(args, "y_shift", None) is not None
        else config.transform.y_shift,
        italic_angle=getattr(args, "italic_angle", None) or config.transform.italic_angle,
    )

    return replace(
        config,
        source=source,
        feature_font_path=resolve_cli_path(getattr(args, "feature_font", None))
        or config.feature_font_path,
        output=output,
        naming=naming,
        unicode=unicode,
        transform=transform,
        temp_dir=resolve_cli_path(getattr(args, "temp_dir", None)) or config.temp_dir,
        allow_incompatible_glyphs=getattr(args, "allow_incompatible_glyphs", False)
        or config.allow_incompatible_glyphs,
    )


def config_from_cli(args: argparse.Namespace) -> CJKBuildConfig:
    """Build a CJK config from direct CLI flags."""
    source_path = resolve_cli_path(getattr(args, "source", None))
    if source_path is None:
        raise ValueError("--source is required when --config is not provided")
    outline_mode = getattr(args, "outline_mode", None) or "auto"
    fixed_axes = parse_axis_assignments(getattr(args, "axis", None))
    output = default_output_for_source(source_path, outline_mode)
    config = CJKBuildConfig(
        source=CJKSourceConfig(
            path=source_path,
            masters=build_master_locations(
                source_path,
                fixed_axes,
                getattr(args, "wght_min", None),
                getattr(args, "wght_regular", None),
                getattr(args, "wght_max", None),
            ),
            outline_mode=outline_mode,
            drop_tables=tuple(getattr(args, "drop_table", None) or ()),
        ),
        feature_font_path=resolve_cli_path(getattr(args, "feature_font", None))
        or Path("source/MapleMono-CN-feature-VF.ttf"),
    )
    return apply_cli_overrides(replace(config, output=output), args)


def config_from_json(config_path: str | Path) -> CJKBuildConfig:
    """Load a CJK build config from JSON."""
    path = Path(config_path)
    data = json.loads(path.read_text())
    base_dir = path.parent

    def resolve_path(value: str | None, default: str) -> Path:
        raw = Path(value or default)
        if raw.is_absolute():
            return raw
        repo_relative = Path.cwd() / raw
        if repo_relative.exists() or str(raw).startswith("source/"):
            return repo_relative
        return base_dir / raw

    source_data = data.get("source", {})
    if not source_data.get("path"):
        raise ValueError("source.path is required")
    outline_mode = source_data.get("outline_mode", "auto")
    if outline_mode not in {"auto", "glyf", "cff2"}:
        raise ValueError("source.outline_mode must be one of: auto, glyf, cff2")

    masters = parse_master_locations(source_data.get("masters"))

    unicode_data = data.get("unicode", {})
    transform_data = data.get("transform", {})
    output_data = data.get("output", {})
    naming_data = data.get("naming", {})

    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=resolve_path(source_data.get("path"), ""),
            masters=masters,
            outline_mode=outline_mode,
            drop_tables=tuple(source_data.get("drop_tables", ())),
        ),
        feature_font_path=resolve_path(
            data.get("feature_font"), "source/MapleMono-CN-feature-VF.ttf"
        ),
        output=CJKOutputConfig(
            dir=resolve_path(output_data.get("dir"), "source/cjk"),
            regular_variable=output_data.get("regular_variable", "MapleMono-CJK-VF.ttf"),
            italic_variable=output_data.get(
                "italic_variable", "MapleMono-CJK-Italic-VF.ttf"
            ),
            static_dir=output_data.get("static_dir", "static"),
            static_hash=output_data.get("static_hash", "static.sha256"),
            archive_name=output_data.get("archive_name", "cjk-base-static.zip"),
        ),
        naming=CJKNamingConfig(
            family_name=naming_data.get("family_name", "Maple Mono CJK"),
            postscript_prefix=naming_data.get("postscript_prefix", "MapleMonoCJK"),
            static_file_prefix=naming_data.get("static_file_prefix", "MapleMonoCJK"),
        ),
        unicode=CJKUnicodeConfig(
            ranges=validate_ranges(
                parse_range(item) for item in unicode_data.get("ranges", [])
            )
            or DEFAULT_CJK_RANGES,
            filter_encoding=unicode_data.get("filter_encoding"),
            exclude_feature_codepoints=unicode_data.get(
                "exclude_feature_codepoints", True
            ),
        ),
        transform=CJKTransformConfig(
            target_advance_width=int(transform_data.get("target_advance_width", 1200)),
            x_scale=float(transform_data.get("x_scale", 1.02)),
            y_scale=float(transform_data.get("y_scale", 1.05)),
            x_shift=int(transform_data.get("x_shift", 100)),
            y_shift=int(transform_data.get("y_shift", -25)),
            italic_angle=float(transform_data.get("italic_angle", 10)),
        ),
        temp_dir=resolve_path(data.get("temp_dir"), "source/cjk/temp"),
        allow_incompatible_glyphs=bool(data.get("allow_incompatible_glyphs", False)),
    )


def build_cjk_from_config_file(
    config_path: str | Path,
    vf_only: bool = False,
    unicode_spec: str | None = None,
) -> None:
    """Build CJK fonts from a JSON config file."""
    build_cjk_fonts(
        apply_unicode_override(config_from_json(config_path), unicode_spec),
        vf_only,
    )


def build_cjk_from_args(args: argparse.Namespace) -> None:
    """Build CJK fonts from JSON config plus CLI overrides or direct CLI flags."""
    if args.config:
        config = config_from_json(args.config)
        config = apply_cli_overrides(config, args)
    else:
        config = config_from_cli(args)
    build_cjk_fonts(
        apply_unicode_override(config, args.unicodes),
        args.vf_only,
    )


def add_cjk_arguments(parser: argparse.ArgumentParser) -> None:
    """Add custom CJK build arguments to an argparse parser."""
    parser.add_argument(
        "--config",
        type=str,
        help="Path to a CJK build JSON config",
    )
    parser.add_argument("--source", help="Source glyf/CFF2 variable font path")
    parser.add_argument(
        "--feature-font",
        help="Feature variable font used as the source of weight/name metadata",
    )
    parser.add_argument(
        "--outline-mode",
        choices=("auto", "glyf", "cff2"),
        help="Expected source outline format",
    )
    parser.add_argument(
        "--axis",
        action="append",
        help="Fixed source axis coordinate, for example ROND=100",
    )
    parser.add_argument("--wght-min", type=float, help="Source minimum wght coordinate")
    parser.add_argument(
        "--wght-regular",
        type=float,
        help="Source regular/default wght coordinate",
    )
    parser.add_argument("--wght-max", type=float, help="Source maximum wght coordinate")
    parser.add_argument(
        "--drop-table",
        action="append",
        help="Source table tag to drop before subsetting; repeat as needed",
    )
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--regular-output", help="Regular variable output file name/path")
    parser.add_argument("--italic-output", help="Italic variable output file name/path")
    parser.add_argument("--static-dir", help="Static font output subdirectory")
    parser.add_argument("--static-hash", help="Static hash file name")
    parser.add_argument("--archive-name", help="Static archive file name")
    parser.add_argument("--family-name", help="Output family name")
    parser.add_argument("--postscript-prefix", help="Output PostScript name prefix")
    parser.add_argument("--static-file-prefix", help="Static font file prefix")
    parser.add_argument("--filter-encoding", help="Optional Unicode encoding filter")
    parser.add_argument(
        "--include-feature-codepoints",
        action="store_true",
        help="Do not exclude codepoints already covered by the feature font",
    )
    parser.add_argument(
        "--unicodes",
        help=(
            "Unicode preset (cn, jp, tc, kr) or pyftsubset-style range, "
            "for example 4E00-9FFF,3000-303F"
        ),
    )
    parser.add_argument("--target-advance-width", type=int, help="Target CJK width")
    parser.add_argument("--x-scale", type=float, help="CJK glyph X scale")
    parser.add_argument("--y-scale", type=float, help="CJK glyph Y scale")
    parser.add_argument("--x-shift", type=int, help="CJK glyph X shift")
    parser.add_argument("--y-shift", type=int, help="CJK glyph Y shift")
    parser.add_argument("--italic-angle", type=float, help="Generated italic angle")
    parser.add_argument("--temp-dir", help="Temporary build directory")
    parser.add_argument(
        "--allow-incompatible-glyphs",
        action="store_true",
        help="Keep incompatible glyf glyphs fixed instead of failing",
    )
    parser.add_argument(
        "--vf-only",
        action="store_true",
        help="only rebuild variable fonts and skip static font generation",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Maple Mono CJK fonts")
    add_cjk_arguments(parser)
    args = parser.parse_args()
    build_cjk_from_args(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field, replace
from os import cpu_count, listdir, makedirs
from pathlib import Path
from typing import Any, Iterable, Literal

from fontTools import subset
from fontTools.subset import parse_unicodes
from fontTools.pens.cu2quPen import Cu2QuMultiPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.varLib.instancer import instantiateVariableFont

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from source.py.task._utils import archive
from source.py.task._utils_vf import (
    _build_weight_variations,
    _glyph_coordinates,
    drop_font_tables,
    get_cmap_codepoints,
    get_unicode_cmap,
    load_font_eager,
    make_italic_master_file,
    make_italic_variable_font,
    merge_masters_into_vf,
    normalize_weight_axis,
    recalculate_font_metrics,
    update_italic_metadata,
    weight_axis,
)
from source.py.utils import get_directory_hash


OutlineMode = Literal["auto", "glyf", "cff2"]
UnicodePreset = Literal["cn", "jp", "tc", "kr"]


STATIC_WEIGHT_MAP: dict[int, str] = {
    100: "Thin",
    210: "ExtraLight",
    320: "Light",
    400: "Regular",
    490: "Medium",
    570: "SemiBold",
    680: "Bold",
    800: "ExtraBold",
}

DEFAULT_WEIGHT_MAPPING_POINTS: tuple[tuple[int, int], ...] = (
    (100, 100),
    (200, 210),
    (300, 320),
    (400, 400),
    (500, 490),
    (600, 570),
    (700, 680),
    (800, 800),
)

DEFAULT_WEIGHT_INSTANCES: tuple[tuple[int, str], ...] = (
    (261, "Thin"),
    (262, "ExtraLight"),
    (263, "Light"),
    (259, "Regular"),
    (265, "Medium"),
    (266, "SemiBold"),
    (267, "Bold"),
    (268, "ExtraBold"),
)

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
class CJKMasterSpec:
    """Static master location used to build output gvar deltas."""

    name: str
    axes: dict[str, float]


@dataclass(frozen=True)
class CJKSourceConfig:
    """Input CJK variable font configuration."""

    path: Path
    masters: tuple[CJKMasterSpec, CJKMasterSpec, CJKMasterSpec]
    outline_mode: OutlineMode = "auto"
    drop_tables: tuple[str, ...] = ()
    cff_to_glyf_max_error: float = 1.0


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
    expected_feature_weight_axis: tuple[int, int, int] = (100, 400, 800)
    output_weight_regular: int = 400
    weight_axis_name_id: int = 256
    weight_axis_name: str = "Weight"
    weight_mapping_points: tuple[tuple[int, int], ...] = DEFAULT_WEIGHT_MAPPING_POINTS
    weight_instances: tuple[tuple[int, str], ...] = DEFAULT_WEIGHT_INSTANCES
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
    master_specs: tuple[CJKMasterSpec, CJKMasterSpec, CJKMasterSpec],
    process_pool: Executor,
    output_suffix: str = ".ttf",
    drop_table_tags: Iterable[str] = (),
) -> tuple[Path, Path, Path]:
    """Instantiate the configured static masters from a variable font."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    futures = []
    for master in master_specs:
        output_path = output_dir / f"{master.name}-master{output_suffix}"
        paths.append(output_path)
        futures.append(
            process_pool.submit(
                instantiate_variable_font_file,
                str(vf_path),
                str(output_path),
                master.axes,
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
    if requested != "auto":
        return requested
    if "glyf" in font:
        return "glyf"
    if "CFF2" in font or "CFF " in font:
        return "cff2"
    raise ValueError("Source font must contain either glyf or CFF/CFF2 outlines")


def convert_cff2_masters_to_glyf(
    master_paths: tuple[Path, Path, Path],
    output_dir: Path,
    config: CJKBuildConfig,
) -> tuple[Path, Path, Path]:
    """Convert compatible static CFF/CFF2 masters to TrueType glyf masters."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fonts = [load_font_eager(path) for path in master_paths]
    output_paths = tuple(
        output_dir / path.name.replace(".otf", ".ttf") for path in master_paths
    )

    try:
        glyph_order = fonts[0].getGlyphOrder()
        glyph_sets = [font.getGlyphSet() for font in fonts]
        glyf_tables = [newTable("glyf") for _ in fonts]
        for glyf in glyf_tables:
            glyf.glyphs = {}
            glyf.setGlyphOrder(glyph_order)

        for glyph_name in glyph_order:
            recordings = []
            for glyph_set in glyph_sets:
                pen = RecordingPen()
                glyph_set[glyph_name].draw(pen)
                recordings.append(pen.value)

            tt_pens = [
                TTGlyphPen(glyph_set, outputImpliedClosingLine=True)
                for glyph_set in glyph_sets
            ]
            multi_pen = Cu2QuMultiPen(
                tt_pens,
                max_err=config.source.cff_to_glyf_max_error,
                reverse_direction=True,
            )
            replay_compatible_recordings(glyph_name, recordings, multi_pen)

            for glyf, tt_pen in zip(glyf_tables, tt_pens):
                glyf.glyphs[glyph_name] = tt_pen.glyph()

        for font, glyf, output_path in zip(fonts, glyf_tables, output_paths):
            font["glyf"] = glyf
            for glyph_name in glyph_order:
                glyph = glyf.glyphs[glyph_name]
                if getattr(glyph, "numberOfContours", 0) > 0:
                    glyph.recalcBounds(glyf)
                else:
                    glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0
            font["loca"] = newTable("loca")
            drop_font_tables(
                font,
                (*config.source.drop_tables, "CFF ", "CFF2", "avar"),
            )
            update_maxp_for_glyf(font)
            font.save(output_path)
        return output_paths
    finally:
        for font in fonts:
            font.close()


def replay_compatible_recordings(
    glyph_name: str, recordings: list[list[tuple[str, tuple]]], multi_pen: Cu2QuMultiPen
) -> None:
    """Replay matching CFF recordings into a Cu2QuMultiPen."""
    first = recordings[0]
    if not all(len(recording) == len(first) for recording in recordings):
        raise ValueError(f"Incompatible contour command count for glyph: {glyph_name}")

    for commands in zip(*recordings):
        operator = commands[0][0]
        if not all(command[0] == operator for command in commands):
            raise ValueError(f"Incompatible contour command for glyph: {glyph_name}")

        args_list = [command[1] for command in commands]
        if operator in {"closePath", "endPath"}:
            getattr(multi_pen, operator)()
        elif operator == "addComponent":
            component_name = args_list[0][0]
            if not all(args[0] == component_name for args in args_list):
                raise ValueError(f"Incompatible component for glyph: {glyph_name}")
            multi_pen.addComponent(component_name, [args[1] for args in args_list])
        else:
            getattr(multi_pen, operator)(args_list)


def update_maxp_for_glyf(font: TTFont) -> None:
    """Populate TrueType maxp fields after CFF/CFF2 to glyf conversion."""
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
    font["maxp"].recalc(font)


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


def prune_stat(font: TTFont, config: CJKBuildConfig) -> None:
    """Prune STAT table to weight axis only."""
    if "STAT" not in font:
        return
    stat = font["STAT"].table
    if getattr(stat, "DesignAxisRecord", None):
        axes = [axis for axis in stat.DesignAxisRecord.Axis if axis.AxisTag == "wght"]
        for axis in axes:
            axis.AxisNameID = config.weight_axis_name_id
            axis.AxisOrdering = 0
        stat.DesignAxisRecord.Axis = axes
        stat.DesignAxisRecord.AxisCount = len(axes)
        stat.DesignAxisCount = len(axes)


def recalculate_font(font: TTFont, config: CJKBuildConfig) -> None:
    """Recalculate common font metrics."""
    recalculate_font_metrics(font)
    if "OS/2" in font:
        font["OS/2"].xAvgCharWidth = config.transform.target_advance_width // 2


def normalize_cjk_weight_axis(font: TTFont, config: CJKBuildConfig) -> None:
    """Normalize the single weight axis for Maple CJK output."""
    normalize_weight_axis(
        font,
        axis_name_id=config.weight_axis_name_id,
        axis_name=config.weight_axis_name,
        instance_weights=[weight for _, weight in config.weight_mapping_points],
        instances=list(config.weight_instances),
        default_value=config.output_weight_regular,
    )


def load_feature_variable_font(input_path: Path, config: CJKBuildConfig) -> TTFont:
    """Load and validate the Maple feature variable font used as merge base."""
    print(f"Loading feature variable font: {input_path}")
    font = load_font_eager(input_path)
    if "fvar" not in font:
        raise ValueError(f"Font is missing fvar table: {input_path}")
    axis = weight_axis(font)
    if not axis:
        raise ValueError(f"Font is missing wght axis: {input_path}")
    values = (float(axis.minValue), float(axis.defaultValue), float(axis.maxValue))
    if values != config.expected_feature_weight_axis:
        expected = "/".join(f"{value:g}" for value in config.expected_feature_weight_axis)
        actual = "/".join(f"{value:g}" for value in values)
        raise ValueError(f"Expected wght axis {expected}, got {actual}: {input_path}")
    return font


def update_variable_font_names(font: TTFont, subfamily: str, config: CJKBuildConfig) -> None:
    """Update variable font naming after merging CJK glyphs into the feature base."""
    family_name = config.naming.family_name
    full_name = f"{family_name} {subfamily}"
    postscript_name = f"{config.naming.postscript_prefix}-{subfamily.replace(' ', '')}"

    name_table = font["name"]
    for name_id in (1, 2, 4, 6, 16, 17, 25):
        name_table.removeNames(nameID=name_id)

    name_table.setName(family_name, 1, 3, 1, 0x409)
    name_table.setName(subfamily, 2, 3, 1, 0x409)
    name_table.setName(full_name, 4, 3, 1, 0x409)
    name_table.setName(postscript_name, 6, 3, 1, 0x409)
    name_table.setName(family_name, 16, 3, 1, 0x409)
    name_table.setName(subfamily, 17, 3, 1, 0x409)
    name_table.setName(config.naming.postscript_prefix, 25, 3, 1, 0x409)


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
    """Instantiate source masters and convert CFF/CFF2 outlines when required."""
    subset_font = load_font_eager(subset_path)
    try:
        outline_mode = detect_outline_mode(subset_font, config.source.outline_mode)
    finally:
        subset_font.close()

    if outline_mode == "cff2":
        cff_master_dir = config.temp_dir / "source-cff-masters"
        cff_master_paths = instantiate_masters_from_vf(
            subset_path,
            cff_master_dir,
            config.source.masters,
            process_pool,
            ".otf",
            config.source.drop_tables,
        )
        return convert_cff2_masters_to_glyf(
            cff_master_paths,
            config.temp_dir / "source-masters",
            config,
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
    prune_stat(font, config)
    recalculate_font(font, config)
    normalize_cjk_weight_axis(font, config)
    prune_stat(font, config)
    recalculate_font(font, config)
    update_variable_font_names(font, subfamily, config)


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
    feature_master_specs = (
        CJKMasterSpec("feature-min", {"wght": config.expected_feature_weight_axis[0]}),
        CJKMasterSpec(
            "feature-regular", {"wght": config.expected_feature_weight_axis[1]}
        ),
        CJKMasterSpec("feature-max", {"wght": config.expected_feature_weight_axis[2]}),
    )
    feature_master_paths = instantiate_masters_from_vf(
        feature_font_path,
        config.temp_dir / "feature-masters",
        feature_master_specs,
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
    weight: int,
    name: str,
    is_italic: bool,
    family_name: str,
    postscript_prefix: str,
) -> None:
    """Instantiate one static CJK font and apply final naming cleanup."""
    print(f"Instantiating {name} {'Italic' if is_italic else ''}...")
    var_font = load_font_eager(input_path)
    instance = instantiateVariableFont(var_font, {"wght": weight}, inplace=False)

    subfamily = (f"{name} Italic" if is_italic else name).replace(
        "Regular Italic", "Italic"
    )

    instance["name"].setName(family_name, 1, 3, 1, 0x409)
    instance["name"].setName(subfamily, 2, 3, 1, 0x409)
    instance["name"].setName(f"{family_name} {subfamily}", 4, 3, 1, 0x409)
    instance["name"].setName(
        f"{postscript_prefix}-{subfamily.replace(' ', '')}",
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


def instantiate_static_fonts(
    config: CJKBuildConfig,
    var_font_names: Iterable[str],
    process_pool: Executor,
) -> Path:
    """Instantiate all static fonts for the generated regular and italic VFs."""
    static_dir = config.output.dir / config.output.static_dir
    makedirs(static_dir, exist_ok=True)
    futures = []
    for font_name in var_font_names:
        is_italic = "Italic" in font_name
        input_path = config.output.dir / font_name
        for weight, name in STATIC_WEIGHT_MAP.items():
            output_name = (
                f"{config.naming.static_file_prefix}-{name}"
                f"{'Italic' if is_italic else ''}.ttf"
            ).replace("RegularItalic", "Italic")
            output_path = static_dir / output_name
            futures.append(
                process_pool.submit(
                    instantiate_static_font_file,
                    str(input_path),
                    str(output_path),
                    weight,
                    name,
                    is_italic,
                    config.naming.family_name,
                    config.naming.postscript_prefix,
                )
            )

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

        regular_font, source_master_paths = build_regular_cjk_font(
            config.feature_font_path,
            config.source.path,
            config,
            process_pool,
        )
        print(f"> Save regular variable font to {regular_output}")
        regular_font.save(regular_output)
        regular_font.close()

        italic_font = build_italic_cjk_font(
            config.feature_font_path,
            source_master_paths,
            config,
            process_pool,
        )
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

    master_data = source_data.get("masters")
    if not isinstance(master_data, list) or len(master_data) != 3:
        raise ValueError("source.masters must contain exactly 3 master entries")
    masters = tuple(
        CJKMasterSpec(
            str(entry.get("name") or f"master-{index}"),
            {str(axis): float(value) for axis, value in entry.get("axes", {}).items()},
        )
        for index, entry in enumerate(master_data)
    )
    if any("wght" not in master.axes for master in masters):
        raise ValueError("Each source master must include a wght axis value")

    unicode_data = data.get("unicode", {})
    transform_data = data.get("transform", {})
    output_data = data.get("output", {})
    naming_data = data.get("naming", {})

    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=resolve_path(source_data.get("path"), ""),
            masters=masters,  # type: ignore
            outline_mode=outline_mode,
            drop_tables=tuple(source_data.get("drop_tables", ())),
            cff_to_glyf_max_error=float(source_data.get("cff_to_glyf_max_error", 1.0)),
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


def config_from_preset(preset: str) -> CJKBuildConfig:
    """Load a built-in CJK preset lazily to keep preset data near wrappers."""
    if preset == "cn-wenyuan":
        from source.py.task.cn_wenyuan import cn_wenyuan_config

        return cn_wenyuan_config("./source/cn")
    if preset == "jp":
        from source.py.task.jp import jp_config

        return jp_config("./source/jp")
    raise ValueError(f"Unknown CJK preset: {preset}")


def build_cjk_from_preset(
    preset: str,
    vf_only: bool = False,
    unicode_spec: str | None = None,
) -> None:
    """Build CJK fonts from a built-in preset."""
    build_cjk_fonts(
        apply_unicode_override(config_from_preset(preset), unicode_spec),
        vf_only,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Maple Mono CJK fonts")
    parser.add_argument(
        "--config",
        type=str,
        default="source/cjk/config.json",
        help="Path to a CJK build JSON config",
    )
    parser.add_argument(
        "--preset",
        choices=("cn-wenyuan", "jp"),
        help="Use a built-in CJK preset instead of a JSON config",
    )
    parser.add_argument(
        "--unicodes",
        help=(
            "Unicode preset (cn, jp, tc, kr) or pyftsubset-style range, "
            "for example 4E00-9FFF,3000-303F"
        ),
    )
    parser.add_argument(
        "--vf-only",
        action="store_true",
        help="only rebuild variable fonts and skip static font generation",
    )
    args = parser.parse_args()
    if args.preset:
        build_cjk_from_preset(args.preset, args.vf_only, args.unicodes)
    else:
        build_cjk_from_config_file(args.config, args.vf_only, args.unicodes)


if __name__ == "__main__":
    main()

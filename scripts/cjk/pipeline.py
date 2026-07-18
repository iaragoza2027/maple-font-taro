#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from multiprocessing import current_process
import sys
import threading
from array import array
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from os import cpu_count, makedirs
from pathlib import Path
from typing import Any, Iterable, Sequence, TypeVar, cast

from fontTools import subset
from fontTools.misc.transform import Transform
from fontTools.pens.cu2quPen import Cu2QuMultiPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib.instancer import instantiateVariableFont

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cjk.config import (
    add_cjk_arguments,
    apply_cli_overrides,
    apply_unicode_override,
    config_from_cli,
    config_from_json,
    detect_outline_mode,
    ordered_master_locations,
)
from scripts.cjk.models import (
    CJKBuildConfig,
    CJKMasterLocations,
    CJKTransformConfig,
    CJKWeightInstance,
)
from scripts.cjk.variable import (
    drop_font_tables,
    get_cmap_codepoints,
    get_unicode_cmap,
    load_font_eager,
    make_italic_master_file,
    make_italic_variable_font,
    merge_masters_into_vf,
    recalculate_font_metrics,
    skew_glyphs,
    update_italic_metadata,
    weight_axis,
)
from scripts.common.files import archive
from scripts.font.types import CFFTable, GlyfTable, HeadTable, SubsetOptions
from scripts.font.operations import get_directory_hash, set_font_name, update_font_names


RESERVED_NAME_IDS = {1, 2, 4, 6, 16, 17, 25}
CFF_GLYPH_CHUNK_SIZE = 256
_T = TypeVar("_T")


@dataclass(frozen=True)
class MasterBuildJob:
    input_path: str
    output_path: str
    axes: dict[str, float]
    static: bool = True
    optimize: bool = False
    drop_table_tags: tuple[str, ...] = ()
    target_upem: int | None = None
    transform_config: CJKBuildConfig | None = None
    convert_cff_to_glyf: bool = True


@dataclass(frozen=True)
class ItalicMasterJob:
    input_path: str
    output_path: str
    axes: dict[str, float]
    italic_angle: float


@dataclass(frozen=True)
class StaticInstanceJob:
    input_path: str
    output_path: str
    coordinate: float
    name: str
    is_italic: bool
    config: CJKBuildConfig


@dataclass(frozen=True)
class SourceBuildState:
    outline_mode: str
    subset_path: Path
    source_codepoints: set[int]
    keep_codepoints: set[int]
    master_paths: tuple[Path, Path, Path]


@dataclass(frozen=True)
class BuildStats:
    added_glyphs: tuple[str, ...]
    added_codepoints: int
    incompatible_glyphs: int = 0


class CFFChunkWorkerState:
    """Worker-local CFF conversion state initialized once per process."""

    fonts: tuple[TTFont, TTFont, TTFont] | None = None
    labels: dict[str, str] | None = None

    @classmethod
    def initialize(cls, input_paths: tuple[str, str, str]) -> None:
        fonts = cast(
            tuple[TTFont, TTFont, TTFont],
            tuple(load_font_eager(path) for path in input_paths),
        )
        cls.fonts = fonts
        cls.labels = glyph_labels(fonts[0], fonts[0].getGlyphOrder())

    @classmethod
    def require(cls) -> tuple[tuple[TTFont, TTFont, TTFont], dict[str, str]]:
        if cls.fonts is None or cls.labels is None:
            raise RuntimeError("CFF glyph chunk worker fonts are not initialized")
        return cls.fonts, cls.labels


class StaticFontCache:
    """Worker-local cache for repeated variable font instantiation."""

    _fonts: dict[tuple[str, int], TTFont] = {}

    @classmethod
    def get(cls, input_path: str) -> TTFont:
        cache_key = (input_path, threading.get_ident())
        font = cls._fonts.get(cache_key)
        if font is None:
            font = load_font_eager(input_path)
            drop_font_tables(font, ("STAT",))
            cls._fonts[cache_key] = font
        return font


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
    font["name"].removeNames(platformID=1)
    return len(font["name"].names) != before


def instantiate_variable_font_file(
    input_path: str,
    output_path: str,
    axes: dict[str, float],
    static: bool = False,
    optimize: bool = True,
    drop_table_tags: Iterable[str] = (),
    target_upem: int | None = None,
    transform_config: CJKBuildConfig | None = None,
    convert_cff_to_glyf: bool = True,
) -> None:
    """Instantiate a variable font from disk and save it to disk."""
    font = load_font_eager(input_path)
    try:
        print(f"Instantiating {input_path} with axes {axes}...")
        instance = instantiateVariableFont(
            font,
            axes,
            inplace=False,
            optimize=optimize,
            static=static,
            downgradeCFF2=static and "CFF2" in font,
        )
        try:
            if target_upem is not None and "head" in instance:
                source_upem = int(cast(HeadTable, instance["head"]).unitsPerEm)
                if source_upem != target_upem:
                    print(f"Scaling source font UPEM: {source_upem} -> {target_upem}")
                    scale_upem(instance, target_upem)
            drop_font_tables(instance, drop_table_tags)
            if transform_config:
                apply_source_master_transform(instance, transform_config)
                normalize_widths(instance, transform_config)
                if convert_cff_to_glyf and "CFF " in instance:
                    convert_cff_static_to_glyf(instance)
                recalculate_font(instance, transform_config)
            instance.save(output_path)
        finally:
            instance.close()
    finally:
        font.close()


def instantiate_variable_font_job(job: MasterBuildJob) -> None:
    """Top-level process-pool entrypoint for source master instantiation."""
    instantiate_variable_font_file(
        job.input_path,
        job.output_path,
        job.axes,
        job.static,
        job.optimize,
        job.drop_table_tags,
        job.target_upem,
        job.transform_config,
        job.convert_cff_to_glyf,
    )


def instantiate_masters_from_vf(
    vf_path: Path,
    output_dir: Path,
    masters: CJKMasterLocations,
    process_pool: Executor,
    output_suffix: str = ".ttf",
    drop_table_tags: Iterable[str] = (),
    target_upem: int | None = None,
    transform_config: CJKBuildConfig | None = None,
    convert_cff_to_glyf: bool = True,
) -> tuple[Path, Path, Path]:
    """Instantiate the configured static masters from a variable font."""
    output_dir.mkdir(parents=True, exist_ok=True)
    futures = []
    paths: list[Path] = []
    for output_weight, axes in ordered_master_locations(masters):
        output_path = output_dir / f"{output_weight}-master{output_suffix}"
        paths.append(output_path)
        job = MasterBuildJob(
            input_path=str(vf_path),
            output_path=str(output_path),
            axes=axes,
            static=True,
            optimize=False,
            drop_table_tags=tuple(drop_table_tags),
            target_upem=target_upem,
            transform_config=transform_config,
            convert_cff_to_glyf=convert_cff_to_glyf,
        )
        futures.append(process_pool.submit(instantiate_variable_font_job, job))
    for future in futures:
        future.result()
    return cast(tuple[Path, Path, Path], tuple(paths))


def instantiate_italic_master_file(
    input_path: str,
    output_path: str,
    axes: dict[str, float],
    italic_angle: float,
) -> None:
    """Instantiate one static master from a VF, skew it, and save it."""
    font = load_font_eager(input_path)
    try:
        print(f"Instantiating italic {input_path} with axes {axes}...")
        instance = instantiateVariableFont(
            font,
            axes,
            inplace=False,
            optimize=False,
            static=True,
            downgradeCFF2="CFF2" in font,
        )
        try:
            skew_glyphs(instance, italic_angle)
            update_italic_metadata(instance, italic_angle)
            recalculate_font_metrics(instance)
            instance.save(output_path)
        finally:
            instance.close()
    finally:
        font.close()


def instantiate_italic_master_job(job: ItalicMasterJob) -> None:
    """Top-level process-pool entrypoint for italic master instantiation."""
    instantiate_italic_master_file(
        job.input_path,
        job.output_path,
        job.axes,
        job.italic_angle,
    )


def instantiate_italic_masters_from_vf(
    vf_path: Path,
    output_dir: Path,
    masters: CJKMasterLocations,
    process_pool: Executor,
    italic_angle: float,
) -> tuple[Path, Path, Path]:
    """Instantiate and skew configured static masters from a variable font."""
    output_dir.mkdir(parents=True, exist_ok=True)
    futures = []
    paths: list[Path] = []
    for output_weight, axes in ordered_master_locations(masters):
        output_path = output_dir / f"{output_weight}-italic-master.ttf"
        paths.append(output_path)
        job = ItalicMasterJob(
            input_path=str(vf_path),
            output_path=str(output_path),
            axes=axes,
            italic_angle=italic_angle,
        )
        futures.append(process_pool.submit(instantiate_italic_master_job, job))
    for future in futures:
        future.result()
    return cast(tuple[Path, Path, Path], tuple(paths))


def subset_font(font: TTFont, codepoints: set[int]) -> None:
    """Subset font to specified Unicode codepoints."""
    if "gvar" in font:
        variations = font["gvar"].variations
        for glyph_name in font.getGlyphOrder():
            if glyph_name not in variations:
                variations[glyph_name] = []
    options = cast(SubsetOptions, subset.Options())
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


def get_allowed_codepoints(source_font: TTFont, config: CJKBuildConfig) -> set[int]:
    """Select source codepoints allowed by configured ranges and encoding."""
    allowed = {
        codepoint
        for codepoint in get_cmap_codepoints(source_font)
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
    try:
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
        return removed
    finally:
        font.close()


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
    """Normalize CJK glyph advance widths without changing outlines."""
    target_glyphs, zero_width_glyphs = width_target_glyphs(
        font, glyph_names, protected_glyphs
    )
    for glyph_name in target_glyphs:
        if glyph_name not in font["hmtx"].metrics:
            continue
        _, lsb = font["hmtx"].metrics[glyph_name]
        width = (
            0
            if glyph_name in zero_width_glyphs
            else config.transform.target_advance_width
        )
        font["hmtx"].metrics[glyph_name] = (width, lsb)
    if "hhea" in font:
        font["hhea"].advanceWidthMax = config.transform.target_advance_width
    if "HVAR" in font:
        del font["HVAR"]


def width_target_glyphs(
    font: TTFont,
    glyph_names: set[str] | None = None,
    protected_glyphs: set[str] | None = None,
) -> tuple[set[str], set[str]]:
    """Resolve glyphs affected by width normalization."""
    cmap = get_unicode_cmap(font)
    zero_width_glyphs = {glyph for cp, glyph in cmap.items() if 0x0300 <= cp <= 0x036F}
    zero_width_glyphs.add(".notdef")
    target_glyphs = (
        glyph_names if glyph_names is not None else set(font.getGlyphOrder())
    )
    if protected_glyphs:
        target_glyphs = target_glyphs - protected_glyphs
    return target_glyphs, zero_width_glyphs


def apply_source_master_transform(font: TTFont, config: CJKBuildConfig) -> None:
    """Apply configured outline transform to a freshly instantiated source master."""
    target_glyphs, zero_width_glyphs = width_target_glyphs(font)
    transform_glyphs = {
        glyph_name
        for glyph_name in target_glyphs
        if glyph_name in font["hmtx"].metrics and glyph_name not in zero_width_glyphs
    }

    if "CFF " in font or "CFF2" in font:
        transform_cff_source_glyphs(font, config.transform, transform_glyphs)
    else:
        for glyph_name in transform_glyphs:
            transform_glyph(font, glyph_name, config.transform)

    if config.transform.x_shift:
        for glyph_name in transform_glyphs:
            advance_width, lsb = font["hmtx"].metrics[glyph_name]
            font["hmtx"].metrics[glyph_name] = (
                advance_width,
                lsb + config.transform.x_shift,
            )


def transform_cff_source_glyphs(
    font: TTFont,
    transform: CJKTransformConfig,
    glyph_names: set[str],
) -> None:
    """Apply configured source-master transform to CFF/CFF2 outlines."""
    transform_cff_glyphs(
        font,
        Transform(
            transform.x_scale,
            0,
            0,
            transform.y_scale,
            transform.x_shift,
            transform.y_shift,
        ),
        glyph_names,
    )


def transform_cff_glyphs(
    font: TTFont,
    glyph_transform: Transform,
    glyph_names: set[str] | None = None,
) -> None:
    """Draw CFF/CFF2 glyphs through an affine transform."""
    table_tag = "CFF2" if "CFF2" in font else "CFF " if "CFF " in font else None
    if table_tag is None:
        return

    is_cff2 = table_tag == "CFF2"
    top_dict = cast(CFFTable, font[table_tag]).cff.topDictIndex[0]
    char_strings = top_dict.CharStrings
    glyph_set = font.getGlyphSet()
    target_glyphs = (
        glyph_names if glyph_names is not None else set(font.getGlyphOrder())
    )

    for glyph_name in target_glyphs:
        if glyph_name not in char_strings or glyph_name not in glyph_set:
            continue
        pen = T2CharStringPen(None, as_fonttools_glyph_mapping(glyph_set), CFF2=is_cff2)
        glyph_set[glyph_name].draw(TransformPen(pen, glyph_transform))
        old_char_string = char_strings[glyph_name]
        char_strings[glyph_name] = pen.getCharString(
            private=old_char_string.private,
            globalSubrs=old_char_string.globalSubrs,
        )


def build_glyf_table(glyph_order: list[str]) -> DefaultTable:
    """Create an empty glyf table for the provided glyph order."""
    table = newTable("glyf")
    glyf = cast(GlyfTable, table)
    glyf.glyphs = {}
    glyf.setGlyphOrder(glyph_order)
    return table


def as_fonttools_glyph_mapping(glyph_set: Any) -> dict[str, Any]:
    """Adapt FontTools' runtime glyph-set mapping to its narrower pen stub type."""
    return cast(dict[str, Any], glyph_set)


def chunked(items: Sequence[_T], chunk_size: int) -> tuple[tuple[_T, ...], ...]:
    """Split items into stable non-empty chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    return tuple(
        tuple(items[index : index + chunk_size])
        for index in range(0, len(items), chunk_size)
    )


def glyph_labels(font: TTFont, glyph_names: Sequence[str]) -> dict[str, str]:
    """Format glyph labels with Unicode context without repeated cmap scans."""
    codepoints_by_glyph: dict[str, list[int]] = {}
    for codepoint, glyph_name in get_unicode_cmap(font).items():
        codepoints_by_glyph.setdefault(glyph_name, []).append(codepoint)

    labels = {}
    for glyph_name in glyph_names:
        codepoints = sorted(codepoints_by_glyph.get(glyph_name, ()))
        if not codepoints:
            labels[glyph_name] = glyph_name
            continue
        unicode_label = ", ".join(f"U+{codepoint:04X}" for codepoint in codepoints[:3])
        if len(codepoints) > 3:
            unicode_label += ", ..."
        labels[glyph_name] = f"{glyph_name} ({unicode_label})"
    return labels


def format_glyph_label(font: TTFont, glyph_name: str) -> str:
    """Format a glyph name with Unicode context when available."""
    return glyph_labels(font, (glyph_name,))[glyph_name]


def reverse_ttglyph_contours(glyph_name: str, glyph):
    """Reverse a quadratic glyph's contour direction without changing point count."""
    if getattr(glyph, "numberOfContours", 0) == 0:
        return glyph
    coordinates = glyph.coordinates
    flags = glyph.flags
    end_points = list(glyph.endPtsOfContours)
    reversed_coordinates: list[tuple[int | float, int | float]] = []
    reversed_flags = array("B")
    rebuilt_end_points: list[int] = []
    start = 0
    for end in end_points:
        contour_coordinates = list(coordinates[start : end + 1])
        contour_flags = list(flags[start : end + 1])
        if len(contour_coordinates) > 1:
            contour_coordinates = contour_coordinates[:1] + contour_coordinates[:0:-1]
            contour_flags = contour_flags[:1] + contour_flags[:0:-1]
        reversed_coordinates.extend(contour_coordinates)
        reversed_flags.extend(contour_flags)
        rebuilt_end_points.append(len(reversed_coordinates) - 1)
        start = end + 1
    glyph.coordinates[:] = reversed_coordinates
    glyph.flags = reversed_flags
    glyph.endPtsOfContours = rebuilt_end_points
    return glyph


def record_glyph_commands(
    glyph_set, glyph_name: str
) -> list[tuple[str, tuple[Any, ...]]]:
    """Record segment-pen commands for one glyph."""
    pen = RecordingPen()
    glyph_set[glyph_name].draw(pen)
    return pen.value


def validate_compatible_glyph_commands(
    glyph_name: str,
    recordings: Sequence[list[tuple[str, tuple[Any, ...]]]],
) -> None:
    """Require all masters to expose the same segment command structure."""
    if not recordings:
        return
    reference = recordings[0]
    for master_index, recording in enumerate(recordings[1:], start=1):
        if len(recording) != len(reference):
            raise ValueError(
                f"Incompatible source outlines for {glyph_name}: "
                f"command count {len(reference)} != {len(recording)} "
                f"(master index 0 vs {master_index})"
            )
        for op_index, ((ref_op, ref_args), (op, args)) in enumerate(
            zip(reference, recording)
        ):
            if op != ref_op or len(args) != len(ref_args):
                raise ValueError(
                    f"Incompatible source outlines for {glyph_name}: "
                    f"command #{op_index} {ref_op}/{len(ref_args)} != "
                    f"{op}/{len(args)} (master index 0 vs {master_index})"
                )
            if op == "addComponent" and args[0] != ref_args[0]:
                raise ValueError(
                    f"Incompatible source outlines for {glyph_name}: "
                    f"component mismatch {ref_args[0]} != {args[0]} "
                    f"(master index 0 vs {master_index})"
                )


def replay_multi_glyph_commands(
    glyph_name: str,
    recordings: Sequence[list[tuple[str, tuple[Any, ...]]]],
    multi_pen: Cu2QuMultiPen,
) -> None:
    """Replay recorded glyph commands into a multi-master cu2qu pen."""
    validate_compatible_glyph_commands(glyph_name, recordings)
    for commands in zip(*recordings):
        operation = commands[0][0]
        args_list = [args for _, args in commands]
        if operation == "moveTo":
            multi_pen.moveTo(args_list)
        elif operation == "lineTo":
            multi_pen.lineTo(args_list)
        elif operation == "curveTo":
            multi_pen.curveTo(args_list)
        elif operation == "qCurveTo":
            multi_pen.qCurveTo(args_list)
        elif operation == "closePath":
            multi_pen.closePath()
        elif operation == "endPath":
            multi_pen.endPath()
        elif operation == "addComponent":
            component_names = {args[0] for args in args_list}
            if len(component_names) != 1:
                raise ValueError(
                    f"Incompatible source outlines for {glyph_name}: "
                    f"component names differ across masters"
                )
            multi_pen.addComponent(args_list[0][0], [args[1] for args in args_list])
        else:
            raise ValueError(
                f"Unsupported segment operation {operation!r} while converting "
                f"{glyph_name} from CFF to glyf"
            )


def convert_cff_glyphs_from_loaded_fonts(
    fonts: Sequence[TTFont],
    glyph_names: Sequence[str],
    labels: dict[str, str] | None = None,
) -> dict[str, tuple[Any, ...]]:
    """Convert glyphs jointly across loaded compatible CFF masters."""
    glyph_sets = [font.getGlyphSet() for font in fonts]
    labels = labels if labels is not None else glyph_labels(fonts[0], glyph_names)
    converted_glyphs: dict[str, tuple[Any, ...]] = {}

    for glyph_name in glyph_names:
        tt_pens = [
            TTGlyphPen(
                as_fonttools_glyph_mapping(glyph_set),
                outputImpliedClosingLine=True,
            )
            for glyph_set in glyph_sets
        ]
        recordings = [
            record_glyph_commands(glyph_set, glyph_name) for glyph_set in glyph_sets
        ]
        replay_multi_glyph_commands(
            labels[glyph_name],
            recordings,
            Cu2QuMultiPen(tt_pens, max_err=1.0, reverse_direction=False),
        )
        converted_glyphs[glyph_name] = tuple(
            reverse_ttglyph_contours(glyph_name, tt_pen.glyph()) for tt_pen in tt_pens
        )
    return converted_glyphs


def validate_cff_master_fonts(fonts: Sequence[TTFont]) -> list[str]:
    """Validate compatible CFF inputs and return the shared glyph order."""
    if not fonts or "CFF " not in fonts[0]:
        return []
    glyph_order = fonts[0].getGlyphOrder()
    glyph_orders = [font.getGlyphOrder() for font in fonts]
    if any(order != glyph_order for order in glyph_orders[1:]):
        raise ValueError("CFF source master glyph orders must match before cu2qu")
    return glyph_order


def install_glyf_tables(
    fonts: Sequence[TTFont],
    glyph_order: list[str],
    converted_glyphs: dict[str, tuple[Any, ...]],
) -> None:
    """Install converted quadratic glyphs into fonts."""
    glyf_tables = [build_glyf_table(glyph_order) for _ in fonts]
    for glyph_name in glyph_order:
        glyphs = converted_glyphs[glyph_name]
        for glyph, table in zip(glyphs, glyf_tables):
            glyf = cast(GlyfTable, table)
            glyf.glyphs[glyph_name] = glyph
            if getattr(glyph, "numberOfContours", 0) > 0:
                glyph.recalcBounds(glyf)
            else:
                glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0

    for font, table in zip(fonts, glyf_tables):
        font["glyf"] = table
        font["loca"] = newTable("loca")
        drop_font_tables(font, ("CFF ", "CFF2", "VORG", "VVAR", "vhea", "vmtx"))
        update_maxp_for_glyf(font)


def install_existing_glyf_tables(
    fonts: Sequence[TTFont],
    glyf_tables: Sequence[Any],
) -> None:
    """Install already-built glyf tables into fonts."""
    for font, glyf in zip(fonts, glyf_tables):
        font["glyf"] = glyf
        font["loca"] = newTable("loca")
        drop_font_tables(font, ("CFF ", "CFF2", "VORG", "VVAR", "vhea", "vmtx"))
        update_maxp_for_glyf(font)


def convert_cff_fonts_to_glyf(fonts: Sequence[TTFont]) -> None:
    """Convert one or more compatible static CFF fonts to TrueType glyf outlines."""
    glyph_order = validate_cff_master_fonts(fonts)
    if not glyph_order:
        return
    converted_glyphs = convert_cff_glyphs_from_loaded_fonts(fonts, glyph_order)
    install_glyf_tables(fonts, glyph_order, converted_glyphs)


def init_cff_glyph_chunk_worker(input_paths: tuple[str, str, str]) -> None:
    """Load CFF masters once per conversion worker process."""
    CFFChunkWorkerState.initialize(input_paths)


def convert_cff_glyph_chunk_from_worker(
    glyph_names: tuple[str, ...],
) -> dict[str, tuple[Any, ...]]:
    """Convert a glyph chunk using worker-local CFF masters."""
    fonts, labels = CFFChunkWorkerState.require()
    return convert_cff_glyphs_from_loaded_fonts(
        fonts,
        glyph_names,
        labels,
    )


def cff_master_glyph_order(input_paths: tuple[str, str, str]) -> list[str]:
    """Read and validate shared glyph order from CFF master files."""
    expected_order: list[str] | None = None
    for path in input_paths:
        font = load_font_eager(path)
        try:
            if "CFF " not in font:
                return []
            glyph_order = font.getGlyphOrder()
            if expected_order is None:
                expected_order = glyph_order
            elif glyph_order != expected_order:
                raise ValueError(
                    "CFF source master glyph orders must match before cu2qu"
                )
        finally:
            font.close()
    return expected_order or []


def add_converted_glyphs_to_glyf_tables(
    glyf_tables: Sequence[Any],
    converted_glyphs: dict[str, tuple[Any, ...]],
) -> None:
    """Append one converted chunk into output glyf tables."""
    for glyph_name, glyphs in converted_glyphs.items():
        for glyph, glyf in zip(glyphs, glyf_tables):
            glyf.glyphs[glyph_name] = glyph
            if getattr(glyph, "numberOfContours", 0) > 0:
                glyph.recalcBounds(glyf)
            else:
                glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0


def convert_cff_master_files_to_glyf_tables_parallel(
    input_paths: tuple[str, str, str],
    glyph_order: list[str],
    chunk_size: int = CFF_GLYPH_CHUNK_SIZE,
) -> tuple[Any, Any, Any]:
    """Convert compatible CFF masters into glyf tables with glyph chunks."""
    if current_process().name != "MainProcess":
        raise RuntimeError("CFF glyph chunk conversion must run from the main process")
    if not glyph_order:
        return cast(
            tuple[Any, Any, Any], tuple(build_glyf_table([]) for _ in input_paths)
        )

    chunks = chunked(tuple(glyph_order), chunk_size)
    glyf_tables = [build_glyf_table(glyph_order) for _ in input_paths]
    max_workers = min(4, cpu_count() or 4)
    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=init_cff_glyph_chunk_worker,
        initargs=(input_paths,),
    ) as chunk_pool:
        futures = [
            chunk_pool.submit(convert_cff_glyph_chunk_from_worker, glyph_chunk)
            for glyph_chunk in chunks
        ]
        for future in futures:
            add_converted_glyphs_to_glyf_tables(glyf_tables, future.result())

    return cast(tuple[Any, Any, Any], tuple(glyf_tables))


def convert_cff_static_to_glyf(font: TTFont) -> None:
    """Convert a static CFF font to TrueType glyf outlines."""
    convert_cff_fonts_to_glyf((font,))


def convert_cff_master_files_to_glyf(
    input_paths: tuple[str, str, str],
    output_paths: tuple[str, str, str],
    transform_config: CJKBuildConfig | None = None,
) -> None:
    """Convert three compatible CFF source masters to TTF together."""
    glyph_order = cff_master_glyph_order(input_paths)
    glyf_tables = convert_cff_master_files_to_glyf_tables_parallel(
        input_paths,
        glyph_order,
    )
    fonts = [load_font_eager(path) for path in input_paths]
    try:
        install_existing_glyf_tables(fonts, glyf_tables)
        for font, output_path in zip(fonts, output_paths):
            if transform_config is not None:
                apply_source_master_transform(font, transform_config)
                normalize_widths(font, transform_config)
                recalculate_font(font, transform_config)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            font.save(output_path)
    finally:
        for font in fonts:
            font.close()


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


def load_feature_variable_font(input_path: Path) -> TTFont:
    """Load and validate the Maple feature variable font used as merge base."""
    print(f"Loading feature variable font: {input_path}")
    font = load_font_eager(input_path)
    if "fvar" not in font:
        raise ValueError(f"Font is missing fvar table: {input_path}")
    axis = weight_axis(font)
    if axis is None:
        raise ValueError(f"Font is missing wght axis: {input_path}")
    return font


def update_variable_font_names(
    font: TTFont, subfamily: str, config: CJKBuildConfig
) -> None:
    """Update variable font naming after merging CJK glyphs into the feature base."""
    family_name = config.naming.family_name
    full_name = f"{family_name} {subfamily}"
    postscript_name = f"{config.naming.postscript_prefix}-{subfamily.replace(' ', '')}"
    version_str = get_version_name(font)

    name_table = font["name"]
    move_fvar_instances_from_reserved_name_ids(font)
    for name_id in RESERVED_NAME_IDS:
        name_table.removeNames(nameID=name_id)

    update_font_names(
        font=font,
        family_name=family_name,
        style_name=subfamily,
        unique_identifier=get_unique_identifier(version_str, postscript_name),
        full_name=full_name,
        version_str=version_str,
        postscript_name=postscript_name,
        is_skip_subfamily=False,
        preferred_family_name=family_name,
        preferred_style_name=subfamily,
    )
    set_font_name(font, config.naming.postscript_prefix, 25)


def get_version_name(font: TTFont) -> str:
    """Read the existing version name, falling back to a valid name ID 5 value."""
    return font["name"].getDebugName(5) or "Version 1.000"


def get_unique_identifier(version_str: str, postscript_name: str) -> str:
    """Build a stable unique identifier from the updated PostScript name."""
    return f"{version_str};SUBF;{postscript_name};"


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


def prepare_source_masters(
    subset_path: Path,
    config: CJKBuildConfig,
    process_pool: Executor,
    target_upem: int,
    outline_mode: str,
) -> tuple[Path, Path, Path]:
    """Instantiate transformed source masters for the variable-base pipeline."""
    if outline_mode != "cff2":
        return instantiate_masters_from_vf(
            subset_path,
            config.temp_dir / "source-masters",
            config.source.masters,
            process_pool,
            ".ttf",
            target_upem=target_upem,
            transform_config=config,
        )

    cff_master_paths = instantiate_masters_from_vf(
        subset_path,
        config.temp_dir / "source-masters-cff",
        config.source.masters,
        process_pool,
        ".otf",
        target_upem=target_upem,
        convert_cff_to_glyf=False,
    )
    ttf_master_paths = tuple(
        config.temp_dir / "source-masters" / f"{weight}-master.ttf"
        for weight, _ in ordered_master_locations(config.source.masters)
    )
    cff_master_path_strings = (
        str(cff_master_paths[0]),
        str(cff_master_paths[1]),
        str(cff_master_paths[2]),
    )
    ttf_master_path_strings = (
        str(ttf_master_paths[0]),
        str(ttf_master_paths[1]),
        str(ttf_master_paths[2]),
    )
    convert_cff_master_files_to_glyf(
        cff_master_path_strings,
        ttf_master_path_strings,
        config,
    )
    return (ttf_master_paths[0], ttf_master_paths[1], ttf_master_paths[2])


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
    normalize_widths(
        font, config, glyph_names=added_glyphs, protected_glyphs=protected_glyphs
    )
    prune_stat(font)
    recalculate_font(font, config)
    update_variable_font_names(font, subfamily, config)


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


class CJKBuilder:
    """Coordinate the shared CJK build pipeline without holding live fonts."""

    def __init__(self, config: CJKBuildConfig) -> None:
        self.config = config
        self.process_pool: Executor | None = None
        self.regular_output = config.output.dir / config.output.regular_variable
        self.italic_output = config.output.dir / config.output.italic_variable
        self.static_dir = config.output.dir / config.output.static_dir

    def build(self, vf_only: bool = False) -> None:
        print("> Building CJK fonts...")
        self.process_pool = create_font_executor()
        try:
            self.config.output.dir.mkdir(parents=True, exist_ok=True)
            regular_font, source_state = self._build_regular_variable_font()
            try:
                italic_font = self._build_italic_variable_font(source_state)
                try:
                    self._write_variable_outputs(regular_font, italic_font)
                finally:
                    italic_font.close()
            finally:
                regular_font.close()

            if vf_only:
                print("> Skipping static font generation (--vf-only)")
                return

            print("> Instantiating static fonts...")
            static_dir = self._build_static_fonts(
                (
                    self.config.output.regular_variable,
                    self.config.output.italic_variable,
                )
            )
            self._write_static_artifacts(static_dir)
            print("> CJK rebuild complete.")
        finally:
            if self.process_pool is not None:
                self.process_pool.shutdown(wait=True, cancel_futures=True)
                self.process_pool = None

    def _require_process_pool(self) -> Executor:
        if self.process_pool is None:
            raise RuntimeError("CJKBuilder process pool is not initialized")
        return self.process_pool

    def _prepare_source_build_state(
        self,
        feature_font: TTFont,
    ) -> tuple[SourceBuildState, set[str]]:
        base_codepoints = get_cmap_codepoints(feature_font)
        protected_glyphs = set(get_unicode_cmap(feature_font).values())

        source_font = load_font_eager(self.config.source.path)
        try:
            if "fvar" not in source_font:
                raise ValueError(
                    f"Source font must be variable: {self.config.source.path}"
                )
            outline_mode = detect_outline_mode(
                source_font,
                self.config.source.outline_mode,
            )
            source_codepoints = get_cmap_codepoints(source_font)
            keep_codepoints = get_allowed_codepoints(source_font, self.config)
        finally:
            source_font.close()

        if outline_mode == "cff2":
            print("> CFF2 source masters will be converted to glyf TTF")
        print(f"CJK source unicodes: {len(source_codepoints)}")
        print(f"CJK selected unicodes: {len(keep_codepoints)}")

        subset_path = self.config.temp_dir / (
            "source-subset.otf" if outline_mode == "cff2" else "source-subset.ttf"
        )
        removed = prepare_source_subset(
            self.config.source.path,
            keep_codepoints,
            base_codepoints,
            self.config,
            subset_path,
        )
        print(f"Removed base/feature unicodes from CJK subset: {removed}")

        master_paths = prepare_source_masters(
            subset_path,
            self.config,
            self._require_process_pool(),
            int(cast(HeadTable, feature_font["head"]).unitsPerEm),
            outline_mode,
        )
        return (
            SourceBuildState(
                outline_mode=outline_mode,
                subset_path=subset_path,
                source_codepoints=source_codepoints,
                keep_codepoints=keep_codepoints,
                master_paths=master_paths,
            ),
            protected_glyphs,
        )

    def _build_regular_variable_font(self) -> tuple[TTFont, SourceBuildState]:
        feature_font = load_feature_variable_font(self.config.feature_font_path)
        try:
            source_state, protected_glyphs = self._prepare_source_build_state(
                feature_font
            )
            stats = self._merge_master_paths(feature_font, source_state.master_paths)
            self._log_build_stats("Regular", stats)
            finalize_variable_font(
                feature_font,
                set(stats.added_glyphs),
                protected_glyphs,
                "Regular",
                self.config,
            )
            print(f"Regular CJK base font glyphs: {len(feature_font.getGlyphOrder())}")
            print(
                f"Regular CJK base font unicodes: {len(get_cmap_codepoints(feature_font))}"
            )
            return feature_font, source_state
        except Exception:
            feature_font.close()
            raise

    def _build_italic_variable_font(self, source_state: SourceBuildState) -> TTFont:
        feature_font = load_feature_variable_font(self.config.feature_font_path)
        try:
            protected_glyphs = set(get_unicode_cmap(feature_font).values())
            feature_axis = weight_axis(feature_font)
            if feature_axis is None:
                raise ValueError("Feature font is missing wght axis")
            feature_masters = {
                100: {"wght": float(feature_axis.minValue)},
                400: {"wght": float(feature_axis.defaultValue)},
                800: {"wght": float(feature_axis.maxValue)},
            }
            feature_master_paths = instantiate_italic_masters_from_vf(
                self.config.feature_font_path,
                self.config.temp_dir / "feature-italic-masters",
                feature_masters,
                self._require_process_pool(),
                self.config.transform.italic_angle,
            )
            italic_font = make_italic_variable_font(
                feature_font,
                self.config.transform.italic_angle,
                self.config.temp_dir,
                self._require_process_pool(),
                feature_master_paths,
                masters_are_italic=True,
            )
        except Exception:
            feature_font.close()
            raise

        try:
            italic_master_paths = self._build_source_italic_master_paths(
                source_state.master_paths
            )
            stats = self._merge_master_paths(italic_font, italic_master_paths)
            self._log_build_stats("Italic", stats)
            finalize_variable_font(
                italic_font,
                set(stats.added_glyphs),
                protected_glyphs,
                "Italic",
                self.config,
                is_italic=True,
            )
            print(f"Italic CJK base font glyphs: {len(italic_font.getGlyphOrder())}")
            print(
                f"Italic CJK base font unicodes: {len(get_cmap_codepoints(italic_font))}"
            )
            return italic_font
        except Exception:
            italic_font.close()
            raise

    def _build_source_italic_master_paths(
        self,
        source_master_paths: tuple[Path, Path, Path],
    ) -> tuple[Path, Path, Path]:
        italic_master_dir = self.config.temp_dir / "source-italic-masters"
        italic_master_dir.mkdir(parents=True, exist_ok=True)
        italic_master_paths = (
            italic_master_dir / "source-italic-min-master.ttf",
            italic_master_dir / "source-italic-regular-master.ttf",
            italic_master_dir / "source-italic-max-master.ttf",
        )
        futures = []
        for source_path, output_path in zip(source_master_paths, italic_master_paths):
            futures.append(
                self._require_process_pool().submit(
                    make_italic_master_file,
                    str(source_path),
                    str(output_path),
                    self.config.transform.italic_angle,
                )
            )
        for future in futures:
            future.result()
        return italic_master_paths

    def _merge_master_paths(
        self,
        base_font: TTFont,
        master_paths: tuple[Path, Path, Path],
    ) -> BuildStats:
        masters = [load_font_eager(master_path) for master_path in master_paths]
        try:
            added, added_codepoints = merge_masters_into_vf(
                base_font,
                masters[0],
                masters[1],
                masters[2],
            )
            return BuildStats(
                added_glyphs=tuple(added),
                added_codepoints=added_codepoints,
            )
        finally:
            for master in masters:
                master.close()

    def _log_build_stats(self, label: str, stats: BuildStats) -> None:
        print(f"{label} CJK path added glyphs: {len(stats.added_glyphs)}")
        print(f"{label} CJK path added unicodes: {stats.added_codepoints}")
        if stats.incompatible_glyphs:
            print(f"{label} CJK path fixed-weight glyphs: {stats.incompatible_glyphs}")

    def _write_variable_outputs(
        self, regular_font: TTFont, italic_font: TTFont
    ) -> None:
        print(f"> Save regular variable font to {self.regular_output}")
        regular_font.save(self.regular_output)
        print(f"> Save italic variable font to {self.italic_output}")
        italic_font.save(self.italic_output)

    def _build_static_fonts(self, var_font_names: Iterable[str]) -> Path:
        static_dir = self.static_dir
        makedirs(static_dir, exist_ok=True)
        futures = []
        feature_font = load_feature_variable_font(self.config.feature_font_path)
        try:
            feature_axis = weight_axis(feature_font)
            if feature_axis is None:
                raise ValueError("Feature font is missing wght axis")
            feature_instances = feature_weight_instances(feature_font)
            for font_name in var_font_names:
                is_italic = "Italic" in font_name
                input_path = self.config.output.dir / font_name
                var_font = load_font_eager(input_path)
                try:
                    var_axis = weight_axis(var_font)
                    if var_axis is None:
                        raise ValueError(
                            "Both variable and feature fonts must contain wght axis"
                        )
                    mapped_instances = tuple(
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
                        for instance in feature_instances
                    )
                finally:
                    var_font.close()

                for instance in mapped_instances:
                    output_name = (
                        f"{self.config.naming.static_file_prefix}-{instance.name}"
                        f"{'Italic' if is_italic else ''}.ttf"
                    ).replace("RegularItalic", "Italic")
                    job = StaticInstanceJob(
                        input_path=str(input_path),
                        output_path=str(static_dir / output_name),
                        coordinate=instance.coordinate,
                        name=instance.name,
                        is_italic=is_italic,
                        config=self.config,
                    )
                    futures.append(
                        self._require_process_pool().submit(
                            instantiate_static_font_job,
                            job,
                        )
                    )
        finally:
            feature_font.close()

        for future in futures:
            future.result()
        return static_dir

    def _write_static_artifacts(self, static_dir: Path) -> None:
        hash_path = self.config.output.dir / self.config.output.static_hash
        with open(hash_path, "w") as file:
            file.write(get_directory_hash(str(static_dir)))
            file.flush()
        print(f"> Update {hash_path}")

        archive(
            str(static_dir),
            str(self.config.output.dir / self.config.output.archive_name),
            lambda path: path.endswith(".ttf"),
        )


def finalize_static_font_instance(
    instance: TTFont,
    output_path: str,
    name: str,
    is_italic: bool,
    config: CJKBuildConfig,
) -> None:
    """Apply static font cleanup and save one instantiated font."""
    subfamily = (f"{name} Italic" if is_italic else name).replace(
        "Regular Italic", "Italic"
    )
    if "CFF " in instance:
        if is_italic:
            update_italic_metadata(instance, config.transform.italic_angle)
        convert_cff_static_to_glyf(instance)
        recalculate_font(instance, config)

    version_str = get_version_name(instance)
    postscript_name = f"{config.naming.postscript_prefix}-{subfamily.replace(' ', '')}"
    update_font_names(
        font=instance,
        family_name=config.naming.family_name,
        style_name=subfamily,
        unique_identifier=get_unique_identifier(version_str, postscript_name),
        full_name=f"{config.naming.family_name} {subfamily}",
        version_str=version_str,
        postscript_name=postscript_name,
        is_skip_subfamily=True,
    )
    drop_font_tables(instance, ("kern", "GPOS"))
    remove_mac_name_records(instance)
    instance.save(output_path)


def get_static_worker_font(input_path: str) -> TTFont:
    """Load each variable font once per worker process or thread."""
    return StaticFontCache.get(input_path)


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
    var_font = get_static_worker_font(input_path)
    instance = instantiateVariableFont(
        var_font,
        {"wght": coordinate},
        inplace=False,
        static=True,
        downgradeCFF2="CFF2" in var_font,
    )
    try:
        finalize_static_font_instance(instance, output_path, name, is_italic, config)
    finally:
        instance.close()


def instantiate_static_font_job(job: StaticInstanceJob) -> None:
    """Top-level process-pool entrypoint for static font instantiation."""
    instantiate_static_font_file(
        job.input_path,
        job.output_path,
        job.coordinate,
        job.name,
        job.is_italic,
        job.config,
    )


def build_cjk_fonts(config: CJKBuildConfig, vf_only: bool = False) -> None:
    """Build regular, italic, and optionally static CJK fonts."""
    CJKBuilder(config).build(vf_only=vf_only)


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
        config = apply_cli_overrides(config_from_json(args.config), args)
    else:
        config = config_from_cli(args)
    build_cjk_fonts(apply_unicode_override(config, args.unicodes), args.vf_only)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Maple Mono CJK fonts")
    add_cjk_arguments(parser)
    args = parser.parse_args()
    build_cjk_from_args(args)


if __name__ == "__main__":
    main()

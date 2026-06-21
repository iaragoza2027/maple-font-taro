from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from os import listdir, makedirs
from pathlib import Path
from typing import Iterable

from fontTools.pens.cu2quPen import Cu2QuMultiPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.varLib.instancer import instantiateVariableFont

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
    normalize_weight_axis,
    update_italic_metadata,
    weight_axis,
)
from source.py.task.cn_wenyuan import (
    apply_horizontal_metrics,
    cleanup_static_font_file,
    instantiate_masters_from_vf,
    normalize_widths,
    prune_stat,
    recalculate_font,
    remove_mac_name_records,
    subset_font,
)
from source.py.utils import get_directory_hash, joinPaths


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

JP_MASTER_WEIGHTS: tuple[tuple[int, str], tuple[int, str], tuple[int, str]] = (
    (200, "min"),
    (400, "regular"),
    (900, "max"),
)


@dataclass(frozen=True)
class JPFontConfig:
    """Configuration constants for JP base font building."""

    DEFAULT_ITALIC_ANGLE: int = 10
    EXPECTED_FEATURE_WEIGHT_AXIS: tuple[int, int, int] = (100, 400, 800)
    OUTPUT_WEIGHT_REGULAR: int = 400
    TEMP_DIR: Path = Path("source/jp/temp")
    WEIGHT_AXIS_NAME_ID: int = 256
    WEIGHT_AXIS_NAME: str = "Weight"
    RESOURCE_HAN_ROND_VALUE: int = 100
    CFF_TO_GLYF_MAX_ERROR: float = 1.0
    SOURCE_DROP_TABLES: tuple[str, ...] = (
        "BASE",
        "GDEF",
        "GPOS",
        "GSUB",
        "HVAR",
        "MVAR",
        "VORG",
        "VVAR",
        "vhea",
        "vmtx",
    )

    # Keep the JP source practical for coding: JIS/CP932 text repertoire, limited
    # to Japanese punctuation, kana, JIS kanji, compatibility forms, and fullwidth
    # variants. This avoids pulling broad CJK extension blocks into the base font.
    DAILY_JP_RANGES: tuple[tuple[int, int], ...] = (
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

    WEIGHT_MAPPING_POINTS: tuple[tuple[int, int], ...] = (
        (100, 100),
        (200, 210),
        (300, 320),
        (400, 400),
        (500, 490),
        (600, 570),
        (700, 680),
        (800, 800),
    )
    WEIGHT_INSTANCES: tuple[tuple[int, str], ...] = (
        (261, "Thin"),
        (262, "ExtraLight"),
        (263, "Light"),
        (259, "Regular"),
        (265, "Medium"),
        (266, "SemiBold"),
        (267, "Bold"),
        (268, "ExtraBold"),
    )
    MAPLE_HHEA_METRICS: dict = field(
        default_factory=lambda: {
            "ascent": 990,
            "descent": -270,
            "lineGap": 0,
            "caretSlopeRise": 1,
            "caretSlopeRun": 0,
            "caretOffset": 0,
        }
    )
    MAPLE_OS2_METRICS: dict = field(
        default_factory=lambda: {
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
    )
    MAPLE_POST_METRICS: dict = field(
        default_factory=lambda: {
            "isFixedPitch": 1,
            "underlinePosition": -125,
            "underlineThickness": 50,
            "italicAngle": 0,
        }
    )
    WIDTH_EXPANSION_OFFSET: int = 100
    VERTICAL_EXPANSION_OFFSET: int = -25


def is_in_ranges(codepoint: int, ranges: Iterable[tuple[int, int]]) -> bool:
    return any(start <= codepoint <= end for start, end in ranges)


def get_cp932_codepoints() -> set[int]:
    """Return Unicode codepoints representable by CP932/JIS daily Japanese text."""
    codepoints: set[int] = set()
    for codepoint in range(0x20, 0x10000):
        try:
            chr(codepoint).encode("cp932")
        except UnicodeEncodeError:
            continue
        codepoints.add(codepoint)
    return codepoints


def get_jp_keep_codepoints(
    jp_source: Path, config: JPFontConfig
) -> tuple[set[int], set[int]]:
    """Load JP source codepoints and select the daily-coding JP subset."""
    source = TTFont(jp_source)
    source_codepoints = get_cmap_codepoints(source)
    source.close()

    cp932_codepoints = get_cp932_codepoints()
    keep_codepoints = {
        codepoint
        for codepoint in source_codepoints
        if codepoint in cp932_codepoints
        and is_in_ranges(codepoint, config.DAILY_JP_RANGES)
    }
    return source_codepoints, keep_codepoints


def prepare_jp_subset(
    jp_source: Path,
    keep_codepoints: set[int],
    excluded_codepoints: set[int],
    config: JPFontConfig,
    out_path: Path,
) -> int:
    """Subset the JP source to codepoints not already provided by the base font."""
    font = load_font_eager(jp_source)
    drop_font_tables(font, config.SOURCE_DROP_TABLES)
    filtered_codepoints = keep_codepoints - excluded_codepoints
    removed = len(keep_codepoints) - len(filtered_codepoints)
    subset_font(font, filtered_codepoints)
    font.save(out_path)
    font.close()
    return removed


def load_feature_variable_font(input_path: Path, config: JPFontConfig) -> TTFont:
    """Load and validate the Maple feature variable font used as merge base."""
    print(f"Loading feature variable font: {input_path}")
    font = load_font_eager(input_path)
    if "fvar" not in font:
        raise ValueError(f"Font is missing fvar table: {input_path}")
    axis = weight_axis(font)
    if not axis:
        raise ValueError(f"Font is missing wght axis: {input_path}")
    values = (float(axis.minValue), float(axis.defaultValue), float(axis.maxValue))
    if values != config.EXPECTED_FEATURE_WEIGHT_AXIS:
        expected = "/".join(
            f"{value:g}" for value in config.EXPECTED_FEATURE_WEIGHT_AXIS
        )
        actual = "/".join(f"{value:g}" for value in values)
        raise ValueError(f"Expected wght axis {expected}, got {actual}: {input_path}")
    return font


def normalize_jp_weight_axis(font: TTFont, config: JPFontConfig) -> None:
    """Normalize the single weight axis for Maple JP output."""
    normalize_weight_axis(
        font,
        axis_name_id=config.WEIGHT_AXIS_NAME_ID,
        axis_name=config.WEIGHT_AXIS_NAME,
        instance_weights=[weight for _, weight in config.WEIGHT_MAPPING_POINTS],
        instances=list(config.WEIGHT_INSTANCES),
        default_value=config.OUTPUT_WEIGHT_REGULAR,
    )


def update_variable_font_names(font: TTFont, subfamily: str) -> None:
    """Update variable font naming after merging JP glyphs into the feature base."""
    family_name = "Maple Mono JP"
    full_name = f"{family_name} {subfamily}"
    postscript_name = f"MapleMonoJP-{subfamily.replace(' ', '')}"
    postscript_prefix = "MapleMonoJP"

    name_table = font["name"]
    for name_id in (1, 2, 4, 6, 16, 17, 25):
        name_table.removeNames(nameID=name_id)

    name_table.setName(family_name, 1, 3, 1, 0x409)
    name_table.setName(subfamily, 2, 3, 1, 0x409)
    name_table.setName(full_name, 4, 3, 1, 0x409)
    name_table.setName(postscript_name, 6, 3, 1, 0x409)
    name_table.setName(family_name, 16, 3, 1, 0x409)
    name_table.setName(subfamily, 17, 3, 1, 0x409)
    name_table.setName(postscript_prefix, 25, 3, 1, 0x409)


def instantiate_resource_han_master_file(
    input_path: str,
    output_path: str,
    weight: int,
    rond: int,
    drop_table_tags: Iterable[str],
) -> None:
    """Instantiate a Resource Han static CFF2 master with ROND pinned."""
    font = load_font_eager(input_path)
    drop_font_tables(font, drop_table_tags)
    print(
        f"Instantiating {input_path} with axes {{'wght': {weight}, 'ROND': {rond}}}..."
    )
    instance = instantiateVariableFont(
        font,
        {"wght": float(weight), "ROND": float(rond)},
        inplace=False,
        optimize=False,
        static=True,
    )
    drop_font_tables(instance, drop_table_tags)
    instance.save(output_path)
    instance.close()
    font.close()


def instantiate_resource_han_masters(
    vf_path: Path,
    output_dir: Path,
    config: JPFontConfig,
    process_pool: Executor,
) -> tuple[Path, Path, Path]:
    """Instantiate Resource Han static masters with ROND fixed at 100."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    futures = []
    for weight, name in JP_MASTER_WEIGHTS:
        output_path = output_dir / f"{name}-master.otf"
        paths.append(output_path)
        futures.append(
            process_pool.submit(
                instantiate_resource_han_master_file,
                str(vf_path),
                str(output_path),
                weight,
                config.RESOURCE_HAN_ROND_VALUE,
                config.SOURCE_DROP_TABLES,
            )
        )
    for future in futures:
        future.result()
    return tuple(paths)  # type: ignore


def convert_cff2_masters_to_glyf(
    master_paths: tuple[Path, Path, Path], output_dir: Path, config: JPFontConfig
) -> tuple[Path, Path, Path]:
    """Convert compatible static CFF2 masters to TrueType glyf masters."""
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
                max_err=config.CFF_TO_GLYF_MAX_ERROR,
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
            drop_font_tables(font, (*config.SOURCE_DROP_TABLES, "CFF ", "CFF2", "avar"))
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
    """Populate TrueType maxp fields after CFF2 to glyf conversion."""
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


def merge_jp_masters_into_vf(
    base: TTFont,
    min_master: TTFont,
    regular_master: TTFont,
    max_master: TTFont,
) -> tuple[list[str], int, int]:
    """Merge JP glyph masters into a VF, keeping Regular for incompatible glyphs."""
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


def build_jp_base_font(
    feature_font_path: Path,
    jp_source: Path,
    config: JPFontConfig,
    process_pool: Executor,
) -> tuple[TTFont, tuple[Path, Path, Path]]:
    """Build the upright JP base VF via the master-merge pipeline."""
    feature_font = load_feature_variable_font(feature_font_path, config)
    base_codepoints = get_cmap_codepoints(feature_font)
    protected_glyphs = set(get_unicode_cmap(feature_font).values())
    source_codepoints, keep_codepoints = get_jp_keep_codepoints(jp_source, config)
    print(f"JP source unicodes: {len(source_codepoints)}")
    print(f"JP selected unicodes: {len(keep_codepoints)}")

    subset_path = config.TEMP_DIR / "jp-subset.ttf"
    subset_path.parent.mkdir(parents=True, exist_ok=True)
    removed = prepare_jp_subset(
        jp_source, keep_codepoints, base_codepoints, config, subset_path
    )
    print(f"Removed base/feature unicodes from JP subset: {removed}")

    cff_master_dir = config.TEMP_DIR / "jp-cff-masters"
    cff_master_paths = instantiate_resource_han_masters(
        subset_path, cff_master_dir, config, process_pool
    )
    glyf_master_dir = config.TEMP_DIR / "jp-masters"
    jp_master_paths = convert_cff2_masters_to_glyf(
        cff_master_paths, glyf_master_dir, config
    )

    min_master = load_font_eager(jp_master_paths[0])
    regular_master = load_font_eager(jp_master_paths[1])
    max_master = load_font_eager(jp_master_paths[2])

    added, added_codepoints, incompatible_glyphs = merge_jp_masters_into_vf(
        feature_font, min_master, regular_master, max_master
    )
    print(f"Regular JP path added glyphs: {len(added)}")
    print(f"Regular JP path added unicodes: {added_codepoints}")
    print(f"Regular JP path fixed-weight glyphs: {incompatible_glyphs}")

    apply_horizontal_metrics(feature_font, config)
    normalize_widths(
        feature_font,
        config,
        glyph_names=set(added),
        protected_glyphs=protected_glyphs,
    )
    prune_stat(feature_font, config)
    recalculate_font(feature_font)
    normalize_jp_weight_axis(feature_font, config)
    prune_stat(feature_font, config)
    recalculate_font(feature_font)
    update_variable_font_names(feature_font, "Regular")

    print(f"Regular JP base font glyphs: {len(feature_font.getGlyphOrder())}")
    print(f"Regular JP base font unicodes: {len(get_cmap_codepoints(feature_font))}")

    min_master.close()
    regular_master.close()
    max_master.close()

    return feature_font, jp_master_paths


def instantiate_static_font_file(
    input_path: str, output_path: str, weight: int, name: str, is_italic: bool
) -> None:
    """Instantiate one static Maple JP font and apply final cleanup."""
    print(f"Instantiating {name} {'Italic' if is_italic else ''}...")
    var_font = load_font_eager(input_path)
    instance = instantiateVariableFont(var_font, {"wght": weight}, inplace=False)

    family_name = "Maple Mono JP"
    subfamily = (f"{name} Italic" if is_italic else name).replace(
        "Regular Italic", "Italic"
    )

    instance["name"].setName(family_name, 1, 3, 1, 0x409)
    instance["name"].setName(subfamily, 2, 3, 1, 0x409)
    instance["name"].setName(f"{family_name} {subfamily}", 4, 3, 1, 0x409)
    instance["name"].setName(
        f"{family_name.replace(' ', '')}-{subfamily.replace(' ', '')}",
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


def instantiate_jp_static_fonts(
    base_dir: str,
    static_dir: str,
    var_font_names: Iterable[str],
    process_pool: Executor,
) -> None:
    """Instantiate all static Maple JP fonts in the shared process pool."""
    makedirs(static_dir, exist_ok=True)
    futures = []
    for font_name in var_font_names:
        is_italic = "Italic" in font_name
        input_path = joinPaths(base_dir, font_name)
        for weight, name in STATIC_WEIGHT_MAP.items():
            output_name = (
                f"MapleMonoJP-{name}{'Italic' if is_italic else ''}.ttf".replace(
                    "RegularItalic", "Italic"
                )
            )
            output_path = joinPaths(static_dir, output_name)
            futures.append(
                process_pool.submit(
                    instantiate_static_font_file,
                    input_path,
                    output_path,
                    weight,
                    name,
                    is_italic,
                )
            )

    for future in futures:
        future.result()


def create_jp_executor() -> Executor:
    """Create a shared executor, falling back when process pools are unavailable."""
    try:
        return ProcessPoolExecutor(max_workers=4)
    except (OSError, PermissionError):
        print("> Process pool unavailable; falling back to thread pool")
        return ThreadPoolExecutor(max_workers=4)


def jp(jp_root: str, vf_only: bool = True) -> None:
    print("> Building JP fonts...")
    process_pool: Executor | None = None

    try:
        config = JPFontConfig()
        process_pool = create_jp_executor()
        feature_font_path = Path("source/MapleMono-CN-feature-VF.ttf")
        jp_source = Path(jp_root) / "ResourceHanRoundedJP-VF.otf"

        var_output = joinPaths(jp_root, "MapleMono-JP-VF.ttf")
        var_italic_output = joinPaths(jp_root, "MapleMono-JP-Italic-VF.ttf")

        jp_regular, jp_master_paths = build_jp_base_font(
            feature_font_path, jp_source, config, process_pool
        )
        print(f"> Save regular variable font to {var_output}")
        jp_regular.save(var_output)
        jp_regular.close()

        feature_fresh = load_feature_variable_font(feature_font_path, config)
        protected_glyphs = set(get_unicode_cmap(feature_fresh).values())
        feature_master_dir = config.TEMP_DIR / "feature-masters"
        feature_master_specs = (
            ({"wght": config.EXPECTED_FEATURE_WEIGHT_AXIS[0]}, "feature-min"),
            (
                {"wght": config.EXPECTED_FEATURE_WEIGHT_AXIS[1]},
                "feature-regular",
            ),
            ({"wght": config.EXPECTED_FEATURE_WEIGHT_AXIS[2]}, "feature-max"),
        )
        feature_master_paths = instantiate_masters_from_vf(
            feature_font_path,
            feature_master_dir,
            feature_master_specs,
            process_pool,
        )
        jp_italic = make_italic_variable_font(
            feature_fresh,
            config.DEFAULT_ITALIC_ANGLE,
            config.TEMP_DIR,
            process_pool,
            feature_master_paths,
        )
        feature_fresh.close()

        italic_master_dir = config.TEMP_DIR / "jp-italic-masters"
        italic_master_dir.mkdir(parents=True, exist_ok=True)
        italic_futures = []
        italic_master_paths: list[Path] = []
        for index, name in enumerate(("min", "regular", "max")):
            out_path = italic_master_dir / f"jp-italic-{name}-master.ttf"
            italic_master_paths.append(out_path)
            italic_futures.append(
                process_pool.submit(
                    make_italic_master_file,
                    str(jp_master_paths[index]),
                    str(out_path),
                    config.DEFAULT_ITALIC_ANGLE,
                )
            )
        for future in italic_futures:
            future.result()

        slanted_min = load_font_eager(italic_master_paths[0])
        slanted_regular = load_font_eager(italic_master_paths[1])
        slanted_max = load_font_eager(italic_master_paths[2])

        (
            added_italic,
            added_italic_codepoints,
            incompatible_italic_glyphs,
        ) = merge_jp_masters_into_vf(
            jp_italic, slanted_min, slanted_regular, slanted_max
        )
        print(f"Italic JP path added glyphs: {len(added_italic)}")
        print(f"Italic JP path added unicodes: {added_italic_codepoints}")
        print(f"Italic JP path fixed-weight glyphs: {incompatible_italic_glyphs}")

        apply_horizontal_metrics(jp_italic, config)
        update_italic_metadata(jp_italic, config.DEFAULT_ITALIC_ANGLE)
        normalize_widths(
            jp_italic,
            config,
            glyph_names=set(added_italic),
            protected_glyphs=protected_glyphs,
        )
        prune_stat(jp_italic, config)
        recalculate_font(jp_italic)
        normalize_jp_weight_axis(jp_italic, config)
        prune_stat(jp_italic, config)
        recalculate_font(jp_italic)

        slanted_min.close()
        slanted_regular.close()
        slanted_max.close()

        print(f"Italic JP base font glyphs: {len(jp_italic.getGlyphOrder())}")
        print(f"Italic JP base font unicodes: {len(get_cmap_codepoints(jp_italic))}")

        print(f"> Save italic variable font to {var_italic_output}")
        update_variable_font_names(jp_italic, "Italic")
        jp_italic.save(var_italic_output)
        jp_italic.close()

        if vf_only:
            print("> Skipping static font generation (--vf-only)")
            return

        static_dir = joinPaths(jp_root, "static")
        var_font_names = [
            "MapleMono-JP-VF.ttf",
            "MapleMono-JP-Italic-VF.ttf",
        ]

        print("> Instantiating static fonts...")
        instantiate_jp_static_fonts(jp_root, static_dir, var_font_names, process_pool)

        for filename in listdir(static_dir):
            font_path = joinPaths(static_dir, filename)
            if Path(font_path).is_file() and filename.endswith(".ttf"):
                cleanup_static_font_file(font_path)
        with open(f"{static_dir}.sha256", "w") as file:
            file.write(get_directory_hash(static_dir))
            file.flush()
        print(f"> Update {static_dir}.sha256")
        print("> JP rebuild complete.")

        archive(
            static_dir,
            joinPaths(jp_root, "jp-base-static.zip"),
            lambda path: path.endswith(".ttf"),
        )
    finally:
        if process_pool:
            process_pool.shutdown(wait=True, cancel_futures=True)

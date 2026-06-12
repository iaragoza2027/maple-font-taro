from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from os import cpu_count, listdir, makedirs
from pathlib import Path
from typing import Iterable

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from source.py.task._utils_vf import (
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
from source.py.task._utils import archive
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

MASTER_WEIGHTS: tuple[tuple[int, str], tuple[int, str], tuple[int, str]] = (
    (200, "min"),
    (450, "regular"),
    (900, "max"),
)


class FontBuildProcessPool:
    """Manage the shared process pool used for font instantiation."""

    _PROCESS_POOL: ProcessPoolExecutor | None = None

    @classmethod
    def get_process_pool(cls) -> ProcessPoolExecutor:
        if cls._PROCESS_POOL is None:
            cls._PROCESS_POOL = ProcessPoolExecutor(
                max_workers=min(4, cpu_count() or 4)
            )
        return cls._PROCESS_POOL

    @classmethod
    def shutdown(cls) -> None:
        if cls._PROCESS_POOL is not None:
            cls._PROCESS_POOL.shutdown(wait=True, cancel_futures=True)
            cls._PROCESS_POOL = None


@dataclass(frozen=True)
class FontConfig:
    """Configuration constants for WenYuan CN font building."""

    DEFAULT_ITALIC_ANGLE: int = 10
    EXPECTED_WEIGHT_AXIS: tuple[int, int, int] = (100, 400, 800)
    OUTPUT_WEIGHT_REGULAR: int = 400
    DROP_TABLES: tuple[str, ...] = ("BASE", "VVAR", "vhea", "vmtx")
    TEMP_DIR: Path = Path("source/cn/temp")
    WIDTH_EXPANSION_OFFSET: int = 100
    VERTICAL_EXPANSION_OFFSET: int = -25
    WEIGHT_AXIS_NAME_ID: int = 256
    WEIGHT_AXIS_NAME: str = "Weight"

    BROAD_CJK_RANGES: tuple[tuple[int, int], ...] = (
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


def remove_mac_name_records(font: TTFont) -> bool:
    """Remove legacy Mac name records from a font."""
    if "name" not in font:
        return False
    before = len(font["name"].names)
    font["name"].removeNames(platformID=1)  # type: ignore
    return len(font["name"].names) != before


def cleanup_static_font_file(font_path: str) -> None:
    """Apply inline cleanup to a saved static font file."""
    font = load_font_eager(font_path)
    changed = drop_font_tables(font, ("kern", "GPOS"))
    changed = remove_mac_name_records(font) or changed
    if changed:
        font.save(font_path)
    font.close()


def instantiate_variable_font_file(
    input_path: str,
    output_path: str,
    axes: dict[str, int],
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


def get_wenyuan_keep_codepoints(
    wenyuan_source: Path, config: FontConfig
) -> tuple[set[int], set[int]]:
    """Load WenYuan source codepoints and the filtered keep set."""
    source = TTFont(wenyuan_source)
    source_codepoints = get_cmap_codepoints(source)
    source.close()
    allowed: set[int] = set()
    for start, end in config.BROAD_CJK_RANGES:
        allowed.update(cp for cp in source_codepoints if start <= cp <= end)
    return source_codepoints, allowed


def prepare_wenyuan_subset(
    wenyuan_source: Path,
    keep_codepoints: set[int],
    excluded_glyphs: set[str],
    out_path: Path,
) -> int:
    """Subset the WenYuan source to CJK codepoints, remove overlapping feature
    glyphs, and save the result to *out_path*.  Returns the number of removed
    glyphs for logging.
    """
    font = load_font_eager(wenyuan_source)
    subset_font(font, keep_codepoints)
    removed = keep_only_unicode_glyphs(font, excluded_glyphs)
    font.save(out_path)
    font.close()
    return removed


def instantiate_masters_from_vf(
    vf_path: Path,
    output_dir: Path,
    master_specs: tuple[tuple[dict[str, int], str], ...],
    process_pool: ProcessPoolExecutor,
) -> tuple[Path, Path, Path]:
    """Instantiate static masters from a variable font.

    Each ``master_specs`` entry is an ``({axis: value}, name_stem)`` pair.
    Masters are saved as ``output_dir / {name_stem}-master.ttf``.
    Returns output paths in the same order as *master_specs*.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    futures = []
    for axes, name in master_specs:
        output_path = output_dir / f"{name}-master.ttf"
        paths.append(output_path)
        futures.append(
            process_pool.submit(
                instantiate_variable_font_file,
                str(vf_path),
                str(output_path),
                axes,
                True,
                False,
            )
        )
    for future in futures:
        future.result()
    return tuple(paths)  # type: ignore


def instantiate_static_font_file(
    input_path: str, output_path: str, weight: int, name: str, is_italic: bool
) -> None:
    """Instantiate one static WenYuan CN font and apply final cleanup."""
    print(f"Instantiating {name} {'Italic' if is_italic else ''}...")
    var_font = load_font_eager(input_path)
    instance = instantiateVariableFont(var_font, {"wght": weight}, inplace=False)

    family_name = "Maple Mono CN"
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


def apply_horizontal_metrics(font: TTFont, config: FontConfig) -> None:
    """Apply Maple Mono metrics to font."""
    for attr, value in config.MAPLE_HHEA_METRICS.items():
        setattr(font["hhea"], attr, value)
    for attr, value in config.MAPLE_OS2_METRICS.items():
        if hasattr(font["OS/2"], attr):
            setattr(font["OS/2"], attr, value)
    for attr, value in config.MAPLE_POST_METRICS.items():
        setattr(font["post"], attr, value)


def move_glyph(font: TTFont, glyph_name: str, h_shift: int, v_shift: int) -> None:
    """Move and scale glyph coordinates."""
    if "glyf" not in font or h_shift == 0:
        return
    glyf = font["glyf"]
    glyph = glyf[glyph_name]
    if glyph.isComposite():
        for component in glyph.components:
            if hasattr(component, "x"):
                component.x += h_shift
            elif hasattr(component, "arg1") and not component.flags & 0x0002:
                component.arg1 += h_shift
    elif getattr(glyph, "numberOfContours", 0) > 0:
        coordinates = glyph.coordinates
        if coordinates is None:
            coordinates, _, _ = glyph.getCoordinates(glyf)
            glyph.coordinates = coordinates
        coordinates.scale((1.02, 1.05))
        coordinates.translate((h_shift, v_shift))
    glyph.recalcBounds(glyf)


def normalize_widths(
    font: TTFont,
    config: FontConfig,
    glyph_names: set[str] | None = None,
) -> None:
    """Normalize glyph widths to 1200 or 0.

    If *glyph_names* is given only those glyphs are processed;
    combining-mark / ``.notdef`` detection always uses the full cmap.
    Global tail (``hhea.advanceWidthMax``, HVAR deletion) runs unconditionally.
    """
    cmap = get_unicode_cmap(font)
    zero_width_glyphs = {glyph for cp, glyph in cmap.items() if 0x0300 <= cp <= 0x036F}
    zero_width_glyphs.add(".notdef")
    target_glyphs = (
        glyph_names if glyph_names is not None else set(font.getGlyphOrder())
    )
    for glyph_name in target_glyphs:
        if glyph_name not in font["hmtx"].metrics:
            continue
        _, lsb = font["hmtx"].metrics[glyph_name]
        width = 0 if glyph_name in zero_width_glyphs else 1200
        if width:
            move_glyph(
                font,
                glyph_name,
                config.WIDTH_EXPANSION_OFFSET,
                config.VERTICAL_EXPANSION_OFFSET,
            )
            lsb += config.WIDTH_EXPANSION_OFFSET
        font["hmtx"].metrics[glyph_name] = (width, lsb)
    if "hhea" in font:
        font["hhea"].advanceWidthMax = 1200
    if "HVAR" in font:
        del font["HVAR"]


def prune_stat(font: TTFont, config: FontConfig) -> None:
    """Prune STAT table to weight axis only."""
    if "STAT" not in font:
        return
    stat = font["STAT"].table
    if getattr(stat, "DesignAxisRecord", None):
        axes = [axis for axis in stat.DesignAxisRecord.Axis if axis.AxisTag == "wght"]
        for axis in axes:
            axis.AxisNameID = config.WEIGHT_AXIS_NAME_ID
            axis.AxisOrdering = 0
        stat.DesignAxisRecord.Axis = axes
        stat.DesignAxisRecord.AxisCount = len(axes)
        stat.DesignAxisCount = len(axes)


def subset_font(font: TTFont, codepoints: set[int]) -> None:
    """Subset font to specified codepoints."""
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


def keep_only_unicode_glyphs(font: TTFont, excluded_glyphs: set[str]) -> int:
    """Remove glyphs that exist in excluded set."""
    glyphs = {".notdef", *get_unicode_cmap(font).values()}
    removed_glyphs = (glyphs - {".notdef"}) & excluded_glyphs
    glyphs -= removed_glyphs
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
    sub.populate(glyphs=glyphs)
    sub.subset(font)
    return len(removed_glyphs)


def recalculate_font(font: TTFont) -> None:
    """Recalculate font metrics and keep Maple CN average width stable."""
    recalculate_font_metrics(font)
    if "OS/2" in font:
        font["OS/2"].xAvgCharWidth = 600


def normalize_cn_weight_axis(font: TTFont, config: FontConfig) -> None:
    """Normalize the single weight axis for Maple CN output."""
    normalize_weight_axis(
        font,
        axis_name_id=config.WEIGHT_AXIS_NAME_ID,
        axis_name=config.WEIGHT_AXIS_NAME,
        instance_weights=[weight for _, weight in config.WEIGHT_MAPPING_POINTS],
        instances=list(config.WEIGHT_INSTANCES),
        default_value=config.OUTPUT_WEIGHT_REGULAR,
    )


def load_variable_font(input_path: Path, config: FontConfig) -> TTFont:
    """Load and validate variable font."""
    print(f"Loading variable font: {input_path}")
    font = load_font_eager(input_path)
    if "fvar" not in font:
        raise ValueError(f"Font is missing fvar table: {input_path}")
    axis = weight_axis(font)
    if not axis:
        raise ValueError(f"Font is missing wght axis: {input_path}")
    values = (float(axis.minValue), float(axis.defaultValue), float(axis.maxValue))
    if values != config.EXPECTED_WEIGHT_AXIS:
        expected = "/".join(f"{value:g}" for value in config.EXPECTED_WEIGHT_AXIS)
        actual = "/".join(f"{value:g}" for value in values)
        raise ValueError(f"Expected wght axis {expected}, got {actual}: {input_path}")
    return font


def glyphs_from_fonts(paths: Iterable[Path]) -> set[str]:
    """Extract all glyph names from fonts."""
    glyphs: set[str] = set()
    for font_path in paths:
        font = TTFont(font_path)
        glyphs.update(font.getGlyphOrder())
        font.close()
    glyphs.discard(".notdef")
    return glyphs


def build_cn_base_font(
    feature_font_path: Path,
    wenyuan_source: Path,
    config: FontConfig,
    process_pool: ProcessPoolExecutor,
) -> tuple[TTFont, tuple[Path, Path, Path]]:
    """Build the upright CN extension VF via the master-merge pipeline.

    1. Subset the WenYuan source to CJK codepoints, drop overlapping feature glyphs.
    2. Instantiate 3 static upright WenYuan masters from the subset.
    3. Merge those masters directly into the feature font, computing *gvar*
       deltas inline per added glyph.
    4. Post-process: metrics, width normalization (scoped to added glyphs),
       prune STAT, normalize the weight axis.

    Returns ``(merged_font, wenyuan_master_paths)`` — the three saved upright
    WenYuan master paths are reused by the italic path.
    """
    # 1. Compute excluded glyphs and keep codepoints
    excluded_glyphs = glyphs_from_fonts([feature_font_path])
    _, keep_codepoints = get_wenyuan_keep_codepoints(wenyuan_source, config)

    # 2. Subset WenYuan source first
    subset_path = config.TEMP_DIR / "wenyuan-subset.ttf"
    removed = prepare_wenyuan_subset(
        wenyuan_source, keep_codepoints, excluded_glyphs, subset_path
    )
    print(f"removed base/feature glyphs from subset: {removed}")

    # 3. Instantiate 3 upright static masters from the subset
    wenyuan_master_dir = config.TEMP_DIR / "wenyuan-masters"
    master_specs = tuple(
        ({"ital": 0, "wght": float(weight)}, name) for weight, name in MASTER_WEIGHTS
    )
    wenyuan_master_paths = instantiate_masters_from_vf(
        subset_path, wenyuan_master_dir, master_specs, process_pool
    )

    min_master = load_font_eager(wenyuan_master_paths[0])
    regular_master = load_font_eager(wenyuan_master_paths[1])
    max_master = load_font_eager(wenyuan_master_paths[2])

    # 4. Load feature font and merge WenYuan masters directly into it
    feature_font = load_variable_font(feature_font_path, config)
    added, added_codepoints = merge_masters_into_vf(
        feature_font, min_master, regular_master, max_master
    )
    print(f"regular path added glyphs: {len(added)}")
    print(f"regular path added unicodes: {added_codepoints}")

    # 5. Post-process (width normalization scoped to added glyphs)
    apply_horizontal_metrics(feature_font, config)
    normalize_widths(feature_font, config, glyph_names=set(added))
    prune_stat(feature_font, config)
    recalculate_font(feature_font)

    # 6. Normalize weight axis
    normalize_cn_weight_axis(feature_font, config)
    prune_stat(feature_font, config)
    recalculate_font(feature_font)

    print(f"regular CN extension glyphs: {len(feature_font.getGlyphOrder())}")
    print(f"regular CN extension unicodes: {len(get_cmap_codepoints(feature_font))}")

    min_master.close()
    regular_master.close()
    max_master.close()

    return feature_font, wenyuan_master_paths


def instantiate_wenyuan_static_fonts(
    base_dir: str,
    static_dir: str,
    var_font_names: Iterable[str],
    process_pool: ProcessPoolExecutor,
) -> None:
    """Instantiate all static WenYuan CN fonts in the shared process pool."""
    makedirs(static_dir, exist_ok=True)
    futures = []
    for font_name in var_font_names:
        is_italic = "Italic" in font_name
        input_path = joinPaths(base_dir, font_name)
        for weight, name in STATIC_WEIGHT_MAP.items():
            output_name = (
                f"MapleMonoCN-{name}{'Italic' if is_italic else ''}.ttf".replace(
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


def cn_wenyuan(cn_root: str, regenerate_vf: bool = True) -> None:
    print("> Building CN WenYuan extension fonts...")

    try:
        config = FontConfig()
        process_pool = FontBuildProcessPool.get_process_pool()
        feature_font_path = Path("source/MapleMono-CN-feature-VF.ttf")
        wenyuan_source = Path("source/cn/WenYuanRoundedSCVF.ttf")

        var_output = joinPaths(cn_root, "MapleMono-CN-VF.ttf")
        var_italic_output = joinPaths(cn_root, "MapleMono-CN-Italic-VF.ttf")

        if (
            regenerate_vf
            or not Path(var_output).exists()
            or not Path(var_italic_output).exists()
        ):
            # ── Regular path ──
            cn_regular, wenyuan_master_paths = build_cn_base_font(
                feature_font_path, wenyuan_source, config, process_pool
            )
            print(f"> Save regular variable fonts to {var_output}")
            cn_regular.save(var_output)
            cn_regular.close()

            # ── Italic path ──
            # Step A: Italic feature font
            feature_fresh = load_variable_font(feature_font_path, config)
            feature_master_dir = config.TEMP_DIR / "feature-masters"
            feature_master_specs = (
                ({"wght": config.EXPECTED_WEIGHT_AXIS[0]}, "feature-min"),
                ({"wght": config.EXPECTED_WEIGHT_AXIS[1]}, "feature-regular"),
                ({"wght": config.EXPECTED_WEIGHT_AXIS[2]}, "feature-max"),
            )
            feature_master_paths = instantiate_masters_from_vf(
                feature_font_path,
                feature_master_dir,
                feature_master_specs,
                process_pool,
            )
            cn_italic = make_italic_variable_font(
                feature_fresh,
                config.DEFAULT_ITALIC_ANGLE,
                config.TEMP_DIR,
                process_pool,
                feature_master_paths,
            )
            feature_fresh.close()

            # Step B: Italic WenYuan — slant the saved upright masters
            italic_wenyuan_dir = config.TEMP_DIR / "wenyuan-italic-masters"
            italic_wenyuan_dir.mkdir(parents=True, exist_ok=True)
            italic_wenyuan_futures = []
            italic_master_paths: list[Path] = []
            for i, name in enumerate(("min", "regular", "max")):
                out_path = italic_wenyuan_dir / f"wenyuan-italic-{name}-master.ttf"
                italic_master_paths.append(out_path)
                italic_wenyuan_futures.append(
                    process_pool.submit(
                        make_italic_master_file,
                        str(wenyuan_master_paths[i]),
                        str(out_path),
                        config.DEFAULT_ITALIC_ANGLE,
                    )
                )
            for future in italic_wenyuan_futures:
                future.result()

            slanted_min = load_font_eager(italic_master_paths[0])
            slanted_reg = load_font_eager(italic_master_paths[1])
            slanted_max = load_font_eager(italic_master_paths[2])

            # Step C: Merge slanted WenYuan masters into italic feature VF
            added_italic, added_italic_codepoints = merge_masters_into_vf(
                cn_italic, slanted_min, slanted_reg, slanted_max
            )
            print(f"italic path added glyphs: {len(added_italic)}")
            print(f"italic path added unicodes: {added_italic_codepoints}")

            # Step D: Post-process (re-assert italic metadata after
            # apply_horizontal_metrics which sets upright hhea/post values)
            apply_horizontal_metrics(cn_italic, config)
            update_italic_metadata(cn_italic, config.DEFAULT_ITALIC_ANGLE)
            normalize_widths(cn_italic, config, glyph_names=set(added_italic))
            prune_stat(cn_italic, config)
            recalculate_font(cn_italic)
            normalize_cn_weight_axis(cn_italic, config)
            prune_stat(cn_italic, config)
            recalculate_font(cn_italic)

            slanted_min.close()
            slanted_reg.close()
            slanted_max.close()

            print(f"italic CN extension glyphs: {len(cn_italic.getGlyphOrder())}")
            print(
                f"italic CN extension unicodes: {len(get_cmap_codepoints(cn_italic))}"
            )

            # Save VFs
            print(f"> Save italic variable fonts to {var_italic_output}")
            cn_italic.save(var_italic_output)
            cn_italic.close()
        else:
            print(f"> Reusing existing variable fonts from {cn_root}")

        # ── Static output (unchanged from prior pipeline) ──
        static_dir = joinPaths(cn_root, "static-wenyuan")
        var_font_names = [
            "MapleMono-CN-VF.ttf",
            "MapleMono-CN-Italic-VF.ttf",
        ]

        print("> Instantiating static fonts...")
        instantiate_wenyuan_static_fonts(
            cn_root, static_dir, var_font_names, process_pool
        )

        for filename in listdir(static_dir):
            font_path = joinPaths(static_dir, filename)
            if Path(font_path).is_file() and filename.endswith(".ttf"):
                cleanup_static_font_file(font_path)
        with open(f"{static_dir}.sha256", "w") as file:
            file.write(get_directory_hash(static_dir))
            file.flush()
        print(f"> Update {static_dir}.sha256")
        print("> CN WenYuan rebuild complete.")

        archive(
            static_dir,
            joinPaths(cn_root, "cn-base-static-wenyuan.zip"),
            lambda path: path.endswith(".ttf"),
        )
    finally:
        FontBuildProcessPool.shutdown()

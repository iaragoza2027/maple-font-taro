#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.mutator import instantiateVariableFont as mutatorInstantiate


DEFAULT_INPUT = Path("source/cn/WenYuanRoundedSCVF.ttf")
DEFAULT_OUTPUT = Path("source/cn/WenYuanRoundedSCVF-MapleCN.ttf")
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
WEIGHT_AXIS_NAME_ID = 256
WEIGHT_AXIS_NAME = "Weight"
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
    (50, 50),
    (100, 160),
    (200, 240),
    (300, 320),
    (400, 400),
    (500, 490),
    (600, 580),
    (700, 670),
    (800, 800),
)
WEIGHT_INSTANCES = (
    (100, 160, 261, "Thin"),
    (200, 240, 262, "ExtraLight"),
    (300, 320, 263, "Light"),
    (400, 400, 259, "Regular"),
    (500, 490, 265, "Medium"),
    (600, 580, 266, "SemiBold"),
    (700, 670, 267, "Bold"),
    (800, 800, 268, "ExtraBold"),
)
STAT_WEIGHT_VALUES = (
    (261, "Thin", 160, 50, 200, 0),
    (262, "ExtraLight", 240, 200, 280, 0),
    (263, "Light", 320, 280, 360, 0),
    (259, "Regular", 400, 360, 445, 2),
    (265, "Medium", 490, 445, 535, 0),
    (266, "SemiBold", 580, 535, 625, 0),
    (267, "Bold", 670, 625, 735, 0),
    (268, "ExtraBold", 800, 735, 800, 0),
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


def normalized_weight(value: float) -> float:
    if value <= 50:
        return 0
    if value >= 800:
        return 1
    return (value - 50) / 750


def weight_axis_map() -> dict[float, float]:
    result = {-1.0: -1.0}
    result.update(
        {
            normalized_weight(user_weight): normalized_weight(design_weight)
            for user_weight, design_weight in WEIGHT_MAPPING_POINTS
        }
    )
    return result


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


def move_glyph_right(font: TTFont, glyph_name: str, offset: int) -> None:
    if "glyf" not in font or offset == 0:
        return

    glyf = font["glyf"]
    glyph = glyf[glyph_name]
    if glyph.isComposite():
        for component in glyph.components:
            if hasattr(component, "x"):
                component.x += offset
            elif hasattr(component, "arg1") and not component.flags & 0x0002:
                component.arg1 += offset
    elif getattr(glyph, "numberOfContours", 0) > 0:
        coordinates = glyph.coordinates
        if coordinates is None:
            coordinates, _, _ = glyph.getCoordinates(glyf)
            glyph.coordinates = coordinates
        coordinates.translate((offset, 0))

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
            move_glyph_right(font, glyph_name, WIDTH_EXPANSION_OFFSET)
            lsb += WIDTH_EXPANSION_OFFSET
        font["hmtx"].metrics[glyph_name] = (width, lsb)

    if "hhea" in font:
        font["hhea"].advanceWidthMax = 1200

    if "HVAR" in font:
        del font["HVAR"]


def normalize_user_weight(value: float) -> float:
    return normalized_weight(value)


def denormalize_source_weight(norm: float) -> float:
    if norm <= -1:
        return 50
    return 50 + norm * 750


def source_weight_to_public(value: float) -> float:
    return value


def remap_tuple_variation_axis(variation: TupleVariation) -> None:
    peak = variation.axes.get("wght")
    if peak is None:
        return

    remapped = []
    for norm in peak:
        source_weight = denormalize_source_weight(norm)
        public_weight = source_weight_to_public(source_weight)
        remapped.append(normalize_user_weight(public_weight))

    variation.axes["wght"] = tuple(remapped)


def remap_variation_data(font: TTFont) -> None:
    if "gvar" in font:
        for variations in font["gvar"].variations.values():
            for variation in variations:
                remap_tuple_variation_axis(variation)

    if "cvar" in font:
        for variation in font["cvar"].variations:
            remap_tuple_variation_axis(variation)

    # HVAR is removed during width normalization. If widths are preserved, leaving
    # HVAR untouched is safer than partially rewriting device variation stores.


def ensure_gvar_entries(font: TTFont) -> None:
    if "gvar" not in font:
        return

    for glyph_name in font.getGlyphOrder():
        font["gvar"].variations.setdefault(glyph_name, [])


def replace_default_master(font: TTFont, source_weight: float) -> None:
    """Replace the default master with an interpolated instance at source_weight."""
    if "fvar" not in font or "gvar" not in font:
        return

    # Get the current default value (before we change it)
    weight_axis = next((ax for ax in font["fvar"].axes if ax.axisTag == "wght"), None)
    if not weight_axis:
        return

    old_default = weight_axis.defaultValue
    if abs(old_default - source_weight) < 0.01:
        return  # Already at target weight

    # Calculate normalized position
    old_norm = (old_default - weight_axis.minValue) / (
        weight_axis.maxValue - weight_axis.minValue
    )
    new_norm = (source_weight - weight_axis.minValue) / (
        weight_axis.maxValue - weight_axis.minValue
    )
    delta_norm = new_norm - old_norm

    # Apply delta to default master for each glyph
    gvar = font["gvar"]
    glyf = font.get("glyf")
    if not glyf:
        return

    for glyph_name in font.getGlyphOrder():
        variations = gvar.variations.get(glyph_name, [])
        if not variations:
            continue

        glyph = glyf[glyph_name]
        if not hasattr(glyph, "coordinates") or glyph.coordinates is None:
            try:
                coords, _, _ = glyph.getCoordinates(glyf)
            except Exception:
                continue
        else:
            coords = glyph.coordinates

        # Accumulate deltas from all variations that affect this position
        total_delta_x = [0] * len(coords)
        total_delta_y = [0] * len(coords)

        for variation in variations:
            wght_support = variation.axes.get("wght")
            if not wght_support:
                continue

            # Calculate scalar based on where delta_norm falls in the support
            peak = wght_support[1] if len(wght_support) > 1 else wght_support[0]
            if len(wght_support) == 3:
                min_support, peak, max_support = wght_support
            else:
                min_support = max_support = peak

            # Calculate how much this variation contributes
            if delta_norm == 0:
                scalar = 0.0
            elif delta_norm > 0:
                if peak <= 0:
                    scalar = 0.0
                elif delta_norm <= peak:
                    scalar = delta_norm / peak if peak != 0 else 0.0
                elif delta_norm <= max_support:
                    scalar = (max_support - delta_norm) / (max_support - peak) if max_support != peak else 1.0
                else:
                    scalar = 0.0
            else:  # delta_norm < 0
                if peak >= 0:
                    scalar = 0.0
                elif delta_norm >= peak:
                    scalar = delta_norm / peak if peak != 0 else 0.0
                elif delta_norm >= min_support:
                    scalar = (min_support - delta_norm) / (min_support - peak) if min_support != peak else 1.0
                else:
                    scalar = 0.0

            # Apply this variation's deltas
            if scalar != 0 and variation.coordinates is not None:
                for i, coord in enumerate(variation.coordinates):
                    if coord is None:
                        continue
                    if i < len(total_delta_x):
                        dx, dy = coord if isinstance(coord, tuple) else (coord, 0)
                        total_delta_x[i] += dx * scalar
                        total_delta_y[i] += dy * scalar

        # Apply accumulated deltas to the default master
        for i in range(len(coords)):
            x, y = coords[i]
            coords[i] = (x + round(total_delta_x[i]), y + round(total_delta_y[i]))

        glyph.coordinates = coords
        try:
            glyph.recalcBounds(glyf)
        except Exception:
            pass

    # Now adjust all variation deltas to be relative to the new default
    for glyph_name in font.getGlyphOrder():
        variations = gvar.variations.get(glyph_name, [])
        if not variations:
            continue

        glyph = glyf[glyph_name]
        if not hasattr(glyph, "coordinates") or glyph.coordinates is None:
            continue

        for variation in variations:
            wght_support = variation.axes.get("wght")
            if not wght_support or variation.coordinates is None:
                continue

            # Calculate the scalar we already applied
            peak = wght_support[1] if len(wght_support) > 1 else wght_support[0]
            if len(wght_support) == 3:
                min_support, peak, max_support = wght_support
            else:
                min_support = max_support = peak

            if delta_norm == 0:
                scalar = 0.0
            elif delta_norm > 0:
                if peak <= 0:
                    scalar = 0.0
                elif delta_norm <= peak:
                    scalar = delta_norm / peak if peak != 0 else 0.0
                elif delta_norm <= max_support:
                    scalar = (max_support - delta_norm) / (max_support - peak) if max_support != peak else 1.0
                else:
                    scalar = 0.0
            else:
                if peak >= 0:
                    scalar = 0.0
                elif delta_norm >= peak:
                    scalar = delta_norm / peak if peak != 0 else 0.0
                elif delta_norm >= min_support:
                    scalar = (min_support - delta_norm) / (min_support - peak) if min_support != peak else 1.0
                else:
                    scalar = 0.0

            # Subtract the applied delta from the variation
            if scalar != 0:
                new_coords = []
                for i, coord in enumerate(variation.coordinates):
                    if coord is None:
                        new_coords.append(None)
                        continue
                    dx, dy = coord if isinstance(coord, tuple) else (coord, 0)
                    new_coords.append((int(round(dx * (1 - scalar))), int(round(dy * (1 - scalar)))))
                variation.coordinates = new_coords


def normalize_weight_axis(font: TTFont) -> None:
    if "fvar" not in font:
        return

    axes = [axis for axis in font["fvar"].axes if axis.axisTag == "wght"]
    font["fvar"].axes = axes
    if not axes:
        return

    weight_axis = axes[0]
    weight_axis.minValue = 100
    weight_axis.defaultValue = 100
    weight_axis.maxValue = 800
    weight_axis.flags = 0
    weight_axis.axisNameID = WEIGHT_AXIS_NAME_ID
    set_windows_name(font, WEIGHT_AXIS_NAME_ID, WEIGHT_AXIS_NAME)

    roman_instances = [
        instance
        for instance in font["fvar"].instances
        if instance.coordinates.get("ital", 0) == 0
    ]
    instance_by_name_id = {
        instance.subfamilyNameID: instance for instance in roman_instances
    }

    new_instances = []
    for user_weight, _, name_id, name in WEIGHT_INSTANCES:
        instance = instance_by_name_id[name_id]
        instance.coordinates = {"wght": float(user_weight)}
        instance.subfamilyNameID = name_id
        instance.postscriptNameID = 0xFFFF
        set_windows_name(font, name_id, name)
        new_instances.append(instance)
    font["fvar"].instances = new_instances

    if "avar" in font:
        font["avar"].segments = {"wght": weight_axis_map()}

    remap_variation_data(font)


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

    for table_tag in DROP_TABLES:
        if table_tag in font:
            del font[table_tag]

    ensure_gvar_entries(font)
    replace_default_master(font, 160.0)  # 160 in source maps to 100 in user coordinates
    normalize_weight_axis(font)
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
    font = patch_font(args)

    if args.dry_run:
        print("dry-run: output not written")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    font.save(args.output)
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()

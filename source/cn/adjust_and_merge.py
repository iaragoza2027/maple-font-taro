#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fontTools.ttLib import TTFont


def drop_intermediate_masters(font: TTFont, target_default: float) -> None:
    """Drop intermediate masters and set new default value for the weight axis."""
    if "fvar" not in font or "gvar" not in font:
        return

    weight_axis = next((ax for ax in font["fvar"].axes if ax.axisTag == "wght"), None)
    if not weight_axis:
        return

    old_default = weight_axis.defaultValue
    print(f"Changing default from {old_default} to {target_default}")

    # Update the axis default
    weight_axis.defaultValue = target_default

    # We need to shift the default master outlines
    # This is done by instantiating at the target weight and using those outlines
    if abs(old_default - target_default) > 0.01:
        gvar = font["gvar"]
        glyf = font.get("glyf")

        if not glyf:
            return

        # Calculate normalized positions
        axis_min = weight_axis.minValue
        axis_max = weight_axis.maxValue

        old_norm = (old_default - axis_min) / (axis_max - axis_min)
        new_norm = (target_default - axis_min) / (axis_max - axis_min)
        delta_norm = new_norm - old_norm

        print(f"Shifting default master by {delta_norm} in normalized space")

        # Apply deltas to shift the default master
        for glyph_name in font.getGlyphOrder():
            variations = gvar.variations.get(glyph_name, [])
            if not variations:
                continue

            glyph = glyf[glyph_name]
            try:
                if not hasattr(glyph, "coordinates") or glyph.coordinates is None:
                    coords, _, _ = glyph.getCoordinates(glyf)
                else:
                    coords = glyph.coordinates
            except Exception:
                continue

            # Accumulate deltas
            total_delta_x = [0.0] * len(coords)
            total_delta_y = [0.0] * len(coords)

            for variation in variations:
                wght_support = variation.axes.get("wght")
                if not wght_support or variation.coordinates is None:
                    continue

                # Calculate scalar for this variation at delta_norm
                if len(wght_support) == 3:
                    min_s, peak, max_s = wght_support
                elif len(wght_support) == 1:
                    peak = wght_support[0]
                    min_s = max_s = peak
                else:
                    peak = wght_support[1] if len(wght_support) > 1 else wght_support[0]
                    min_s = max_s = peak

                # Calculate scalar
                if delta_norm == 0:
                    scalar = 0.0
                elif delta_norm > 0:
                    if peak <= 0:
                        scalar = 0.0
                    elif delta_norm <= peak:
                        scalar = delta_norm / peak if peak != 0 else 0.0
                    elif delta_norm <= max_s:
                        scalar = (
                            (max_s - delta_norm) / (max_s - peak)
                            if max_s != peak
                            else 1.0
                        )
                    else:
                        scalar = 0.0
                else:  # delta_norm < 0
                    if peak >= 0:
                        scalar = 0.0
                    elif delta_norm >= peak:
                        scalar = delta_norm / peak if peak != 0 else 0.0
                    elif delta_norm >= min_s:
                        scalar = (
                            (min_s - delta_norm) / (min_s - peak)
                            if min_s != peak
                            else 1.0
                        )
                    else:
                        scalar = 0.0

                # Apply deltas
                if scalar != 0:
                    for i, coord in enumerate(variation.coordinates):
                        if coord is None or i >= len(total_delta_x):
                            continue
                        dx, dy = coord if isinstance(coord, tuple) else (coord, 0)
                        total_delta_x[i] += dx * scalar
                        total_delta_y[i] += dy * scalar

            # Apply to default master
            for i, (x, y) in enumerate(coords):
                coords[i] = (x + round(total_delta_x[i]), y + round(total_delta_y[i]))

            glyph.coordinates = coords
            try:
                glyph.recalcBounds(glyf)
            except Exception:
                pass

            # Adjust variation deltas
            for variation in variations:
                wght_support = variation.axes.get("wght")
                if not wght_support or variation.coordinates is None:
                    continue

                if len(wght_support) == 3:
                    min_s, peak, max_s = wght_support
                elif len(wght_support) == 1:
                    peak = wght_support[0]
                    min_s = max_s = peak
                else:
                    peak = wght_support[1] if len(wght_support) > 1 else wght_support[0]
                    min_s = max_s = peak

                if delta_norm == 0:
                    scalar = 0.0
                elif delta_norm > 0:
                    if peak <= 0:
                        scalar = 0.0
                    elif delta_norm <= peak:
                        scalar = delta_norm / peak if peak != 0 else 0.0
                    elif delta_norm <= max_s:
                        scalar = (
                            (max_s - delta_norm) / (max_s - peak)
                            if max_s != peak
                            else 1.0
                        )
                    else:
                        scalar = 0.0
                else:
                    if peak >= 0:
                        scalar = 0.0
                    elif delta_norm >= peak:
                        scalar = delta_norm / peak if peak != 0 else 0.0
                    elif delta_norm >= min_s:
                        scalar = (
                            (min_s - delta_norm) / (min_s - peak)
                            if min_s != peak
                            else 1.0
                        )
                    else:
                        scalar = 0.0

                if scalar != 0:
                    new_coords = []
                    for coord in variation.coordinates:
                        if coord is None:
                            new_coords.append(None)
                            continue
                        dx, dy = coord if isinstance(coord, tuple) else (coord, 0)
                        new_coords.append(
                            (
                                int(round(dx * (1 - scalar))),
                                int(round(dy * (1 - scalar))),
                            )
                        )
                    variation.coordinates = new_coords


def prepare_base_font(input_path: Path, target_default: float = 100) -> TTFont:
    """Adjust the default weight of base font to match target."""
    print(f"Preparing base font: {input_path}")
    font = TTFont(input_path)

    # Check current axis
    if "fvar" not in font:
        print("No fvar table found")
        return font

    weight_axis = next((ax for ax in font["fvar"].axes if ax.axisTag == "wght"), None)
    if not weight_axis:
        print("No wght axis found")
        return font

    print(
        f"Current wght axis: {weight_axis.minValue}/{weight_axis.defaultValue}/{weight_axis.maxValue}"
    )

    # Drop intermediate masters and shift default
    drop_intermediate_masters(font, target_default)

    print(
        f"Adjusted wght axis: {weight_axis.minValue}/{weight_axis.defaultValue}/{weight_axis.maxValue}\n"
    )

    return font


def merge_fonts(base: TTFont, extra: TTFont, output_path: Path) -> None:
    """Merge two variable fonts."""
    # Validate
    if base["head"].unitsPerEm != extra["head"].unitsPerEm:
        raise ValueError(
            f"UPEM mismatch: {base['head'].unitsPerEm} != {extra['head'].unitsPerEm}"
        )

    # Check axes and adjust base font to match extra
    base_axis = next((ax for ax in base["fvar"].axes if ax.axisTag == "wght"), None)
    extra_axis = next((ax for ax in extra["fvar"].axes if ax.axisTag == "wght"), None)

    if base_axis and extra_axis:
        print(
            f"Base axis before: wght {base_axis.minValue}/{base_axis.defaultValue}/{base_axis.maxValue}"
        )
        print(
            f"Extra axis: wght {extra_axis.minValue}/{extra_axis.defaultValue}/{extra_axis.maxValue}"
        )

        # Drop intermediate masters by shifting default to match extra
        if base_axis.defaultValue != extra_axis.defaultValue:
            drop_intermediate_masters(base, extra_axis.defaultValue)

        print(
            f"Base axis after: wght {base_axis.minValue}/{base_axis.defaultValue}/{base_axis.maxValue}"
        )

    # Find glyphs to add
    base_glyphs = set(base.getGlyphOrder())
    extra_glyphs_to_add = [g for g in extra.getGlyphOrder() if g not in base_glyphs]

    print(f"Base glyphs: {len(base_glyphs)}")
    print(f"Extra glyphs to add: {len(extra_glyphs_to_add)}")

    # Merge glyph data
    base_glyf = base["glyf"]
    extra_glyf = extra["glyf"]
    base_hmtx = base["hmtx"]
    extra_hmtx = extra["hmtx"]
    base_gvar = base.get("gvar")
    extra_gvar = extra.get("gvar")

    for glyph_name in extra_glyphs_to_add:
        base_glyf.glyphs[glyph_name] = deepcopy(extra_glyf.glyphs[glyph_name])
        base_hmtx.metrics[glyph_name] = extra_hmtx.metrics[glyph_name]
        if base_gvar and extra_gvar:
            base_gvar.variations[glyph_name] = deepcopy(
                extra_gvar.variations.get(glyph_name, [])
            )

    # Update glyph order
    base.setGlyphOrder(list(base.getGlyphOrder()) + extra_glyphs_to_add)
    base["maxp"].numGlyphs = len(base.getGlyphOrder())

    # Merge cmap
    base_cmap_entries = {}
    for table in base["cmap"].tables:
        if table.isUnicode():
            base_cmap_entries.update(table.cmap)

    extra_cmap_entries = {}
    for table in extra["cmap"].tables:
        if table.isUnicode():
            extra_cmap_entries.update(table.cmap)

    new_mappings = {
        cp: glyph
        for cp, glyph in extra_cmap_entries.items()
        if glyph in extra_glyphs_to_add and cp not in base_cmap_entries
    }

    for table in base["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(new_mappings)

    print(f"Added {len(new_mappings)} new Unicode mappings")

    # Recalculate
    base["hhea"].numberOfHMetrics = len(base["hmtx"].metrics)
    base["hhea"].recalc(base)
    if "OS/2" in base:
        base["OS/2"].recalcAvgCharWidth(base)
        base["OS/2"].recalcUnicodeRanges(base)
        base["OS/2"].recalcCodePageRanges(base)

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(output_path)
    print(f"Saved: {output_path}")
    print(f"Total glyphs: {len(base.getGlyphOrder())}")


if __name__ == "__main__":
    # Prepare base font with adjusted default weight and merge
    base = prepare_base_font(
        Path("fonts/Variable/MapleMono[wght].ttf"), target_default=100
    )
    merge_fonts(
        base,
        TTFont("source/cn/WenYuanRoundedSCVF-MapleCN.ttf"),
        Path("fonts/MapleMono-CN-VF.ttf"),
    )

from os import listdir, makedirs
from pathlib import Path
import shutil
import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Iterable
from source.py.utils import joinPaths
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont, otRound

from fontTools import subset

from source.py.utils import get_directory_hash, run

from source.py.task._utils_vf import (
    get_cmap_codepoints,
    get_unicode_cmap,
    weight_axis,
    normalize_weight_axis,
    rebuild_weight_masters_with_regular_default,
)
from source.py.task.merge_vf import merge_vf


@dataclass(frozen=True)
class FontConfig:
    """Configuration constants for font building."""

    DEFAULT_ITALIC_ANGLE: float = 10
    EXPECTED_WEIGHT_AXIS: tuple[float, float, float] = (100.0, 400.0, 800.0)
    OUTPUT_WEIGHT_REGULAR: int = 400
    DROP_TABLES: tuple[str, ...] = ("BASE", "VVAR", "vhea", "vmtx")
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


class WenYuanProcessor:
    """Processes WenYuan font for integration with Maple Mono."""

    def __init__(self, config: FontConfig | None = None):
        self.config = config or FontConfig()

    def allowed_codepoints(self, source_codepoints: Iterable[int]) -> set[int]:
        """Filter codepoints to CJK ranges only."""
        allowed: set[int] = set()
        for start, end in self.config.BROAD_CJK_RANGES:
            allowed.update(cp for cp in source_codepoints if start <= cp <= end)
        return allowed

    def apply_horizontal_metrics(self, font: TTFont) -> None:
        """Apply Maple Mono metrics to font."""
        for attr, value in self.config.MAPLE_HHEA_METRICS.items():
            setattr(font["hhea"], attr, value)
        for attr, value in self.config.MAPLE_OS2_METRICS.items():
            if hasattr(font["OS/2"], attr):
                setattr(font["OS/2"], attr, value)
        for attr, value in self.config.MAPLE_POST_METRICS.items():
            setattr(font["post"], attr, value)

    def move_glyph(
        self, font: TTFont, glyph_name: str, h_shift: int, v_shift: int
    ) -> None:
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

    def normalize_widths(self, font: TTFont) -> None:
        """Normalize all glyph widths to 1200 or 0."""
        cmap = get_unicode_cmap(font)
        zero_width_glyphs = {
            glyph for cp, glyph in cmap.items() if 0x0300 <= cp <= 0x036F
        }
        zero_width_glyphs.add(".notdef")
        for glyph_name in font.getGlyphOrder():
            if glyph_name not in font["hmtx"].metrics:
                continue
            _, lsb = font["hmtx"].metrics[glyph_name]
            width = 0 if glyph_name in zero_width_glyphs else 1200
            if width:
                self.move_glyph(
                    font,
                    glyph_name,
                    self.config.WIDTH_EXPANSION_OFFSET,
                    self.config.VERTICAL_EXPANSION_OFFSET,
                )
                lsb += self.config.WIDTH_EXPANSION_OFFSET
            font["hmtx"].metrics[glyph_name] = (width, lsb)
        if "hhea" in font:
            font["hhea"].advanceWidthMax = 1200
        if "HVAR" in font:
            del font["HVAR"]

    def prune_stat(self, font: TTFont) -> None:
        """Prune STAT table to weight axis only."""
        if "STAT" not in font:
            return
        stat = font["STAT"].table
        if getattr(stat, "DesignAxisRecord", None):
            axes = [
                axis for axis in stat.DesignAxisRecord.Axis if axis.AxisTag == "wght"
            ]
            for axis in axes:
                axis.AxisNameID = self.config.WEIGHT_AXIS_NAME_ID
                axis.AxisOrdering = 0
            stat.DesignAxisRecord.Axis = axes
            stat.DesignAxisRecord.AxisCount = len(axes)
            stat.DesignAxisCount = len(axes)

    def subset_font(self, font: TTFont, codepoints: set[int]) -> None:
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

    def keep_only_unicode_glyphs(self, font: TTFont, excluded_glyphs: set[str]) -> int:
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

    def recalculate(self, font: TTFont) -> None:
        """Recalculate font metrics."""
        if "OS/2" in font:
            font["OS/2"].recalcAvgCharWidth(font)
            font["OS/2"].recalcUnicodeRanges(font)
            font["OS/2"].recalcCodePageRanges(font)
            font["OS/2"].xAvgCharWidth = 600

    def normalize_wght_axis(self, font: TTFont) -> None:
        """Normalize weight axis with configured values."""
        normalize_weight_axis(
            font,
            axis_name_id=self.config.WEIGHT_AXIS_NAME_ID,
            axis_name=self.config.WEIGHT_AXIS_NAME,
            instance_weights=[
                weight for _, weight in self.config.WEIGHT_MAPPING_POINTS
            ],
            instances=list(self.config.WEIGHT_INSTANCES),
            default_value=self.config.OUTPUT_WEIGHT_REGULAR,
        )

    def load_variable_font(self, input_path: Path) -> TTFont:
        """Load and validate variable font."""
        print(f"Loading variable font: {input_path}")
        font = TTFont(input_path)
        if "fvar" not in font:
            raise ValueError(f"Font is missing fvar table: {input_path}")
        axis = weight_axis(font)
        if not axis:
            raise ValueError(f"Font is missing wght axis: {input_path}")
        values = (float(axis.minValue), float(axis.defaultValue), float(axis.maxValue))
        if values != self.config.EXPECTED_WEIGHT_AXIS:
            expected = "/".join(f"{v:g}" for v in self.config.EXPECTED_WEIGHT_AXIS)
            actual = "/".join(f"{v:g}" for v in values)
            raise ValueError(
                f"Expected wght axis {expected}, got {actual}: {input_path}"
            )
        return font

    def patch_wenyuan(self, wenyuan_source: Path, excluded_glyphs: set[str]) -> TTFont:
        """Prepare WenYuan font for merging."""
        source = TTFont(wenyuan_source)
        source_codepoints = get_cmap_codepoints(source)
        keep_codepoints = self.allowed_codepoints(source_codepoints)
        print(f"source glyphs: {len(source.getGlyphOrder())}")
        print(f"source unicodes: {len(source_codepoints)}")
        print(f"planned unicode keep: {len(keep_codepoints)}")
        print(f"planned unicode drop: {len(source_codepoints - keep_codepoints)}")
        print(f"planned base/feature glyph exclusions: {len(excluded_glyphs)}")

        min_master = instantiateVariableFont(
            source, {"ital": 0, "wght": 200}, inplace=False
        )
        regular_master = instantiateVariableFont(
            source, {"ital": 0, "wght": 450}, inplace=False
        )

        font = instantiateVariableFont(source, {"ital": 0}, inplace=False)
        source.close()
        for table_tag in self.config.DROP_TABLES:
            if table_tag in font:
                del font[table_tag]
            if table_tag in min_master:
                del min_master[table_tag]
            if table_tag in regular_master:
                del regular_master[table_tag]

        rebuild_weight_masters_with_regular_default(
            font, min_master, regular_master, None
        )
        self.normalize_wght_axis(font)
        self.subset_font(font, keep_codepoints)
        if "GSUB" in font:
            del font["GSUB"]
        if "GPOS" in font:
            del font["GPOS"]
        removed_glyphs = self.keep_only_unicode_glyphs(font, excluded_glyphs)
        print(f"removed base/feature glyphs: {removed_glyphs}")
        self.prune_stat(font)
        self.apply_horizontal_metrics(font)
        self.normalize_widths(font)
        self.recalculate(font)
        print(f"patched WenYuan glyphs: {len(font.getGlyphOrder())}")
        print(f"patched WenYuan unicodes: {len(get_cmap_codepoints(font))}")
        return font

    def skew_component(self, component, skew_factor: float) -> None:
        """Apply skew transformation to component."""
        transform = getattr(component, "transform", None)
        if transform is None:
            component.transform = [[1, 0], [skew_factor, 1]]
        else:
            xx, xy = transform[0]
            yx, yy = transform[1]
            component.transform = [
                [xx, xy],
                [yx + skew_factor * xx, yy + skew_factor * xy],
            ]

    def update_italic_metadata(self, font: TTFont, italic_angle_deg: float) -> None:
        """Update font metadata for italic style."""
        if "post" in font:
            font["post"].italicAngle = -italic_angle_deg  # type: ignore
        if "OS/2" in font:
            os2 = font["OS/2"]
            os2.fsSelection = (os2.fsSelection & ~0x40) | 0x01  # type: ignore
        if "head" in font:
            font["head"].macStyle |= 0x02  # type: ignore
        if "hhea" in font:
            hhea = font["hhea"]
            hhea.caretSlopeRise = 1000  # type: ignore
            hhea.caretSlopeRun = otRound(
                math.tan(math.radians(italic_angle_deg)) * 1000
            )  # type: ignore

    def skew_glyphs(self, font: TTFont, italic_angle_deg: float) -> None:
        """Apply skew transformation to all glyphs."""
        skew_factor = math.tan(math.radians(italic_angle_deg))
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
                    self.skew_component(component, skew_factor)
                composite_glyphs.append(glyph_name)
            else:
                if not hasattr(glyph, "coordinates") or glyph.coordinates is None:
                    coordinates, _, _ = glyph.getCoordinates(glyf_table)
                    glyph.coordinates = coordinates
                glyph.coordinates.transform(((1, 0), (skew_factor, 1), (0, 0)))
                glyph.coordinates.translate(
                    (-otRound(skew_factor * advance_width / 2), 0)
                )
                glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax = (
                    glyph.coordinates.calcIntBounds()
                )
                hmtx[glyph_name] = (advance_width, glyph.xMin)
        for glyph_name in composite_glyphs:
            glyph = glyf_table[glyph_name]
            glyph.recalcBounds(glyf_table)
            advance_width, _ = original_metrics.get(glyph_name, (0, 0))
            hmtx[glyph_name] = (advance_width, glyph.xMin)

    def make_italic(self, font: TTFont, italic_angle_deg: float) -> TTFont:
        """Generate italic version of font."""
        italic_font = deepcopy(font)
        skew_factor = math.tan(math.radians(italic_angle_deg))
        print(f"Italic angle: {italic_angle_deg:g} degrees")
        print(f"Skew factor: {skew_factor:.6f}")
        print(
            f"Building italic masters from {len(font.getGlyphOrder())} CN extension glyphs..."
        )

        min_master = instantiateVariableFont(
            italic_font, {"wght": 100}, inplace=False, optimize=False, static=True
        )
        self.skew_glyphs(min_master, italic_angle_deg)
        self.update_italic_metadata(min_master, italic_angle_deg)
        self.recalculate(min_master)

        regular_master = instantiateVariableFont(
            italic_font, {"wght": 400}, inplace=False, optimize=False, static=True
        )
        self.skew_glyphs(regular_master, italic_angle_deg)
        self.update_italic_metadata(regular_master, italic_angle_deg)
        self.recalculate(regular_master)

        max_master = instantiateVariableFont(
            italic_font, {"wght": 800}, inplace=False, optimize=False, static=True
        )
        self.skew_glyphs(max_master, italic_angle_deg)
        self.update_italic_metadata(max_master, italic_angle_deg)
        self.recalculate(max_master)

        rebuild_weight_masters_with_regular_default(
            italic_font, min_master, regular_master, max_master
        )
        self.update_italic_metadata(italic_font, italic_angle_deg)
        self.recalculate(italic_font)
        return italic_font

    def merge_fonts(self, base: TTFont, extra: TTFont, label: str) -> TTFont:
        """Merge extra font into base font."""
        base_axis = weight_axis(base)
        extra_axis = weight_axis(extra)
        print(
            f"{label} base axis: wght {base_axis.minValue:g}/{base_axis.defaultValue:g}/{base_axis.maxValue:g}"
        )
        print(
            f"{label} extra axis: wght {extra_axis.minValue:g}/{extra_axis.defaultValue:g}/{extra_axis.maxValue:g}"
        )
        merged_font, added_glyphs, added_codepoints = merge_vf(base, extra)
        print(f"{label} added glyphs: {len(added_glyphs)}")
        print(f"{label} added unicodes: {added_codepoints}")
        print(f"{label} glyphs: {len(merged_font.getGlyphOrder())}")
        print(f"{label} unicodes: {len(get_cmap_codepoints(merged_font))}")
        return merged_font

    def build_cn_base_font(
        self, feature_font_path: Path, wenyuan_source: Path
    ) -> TTFont:
        """Build Chinese extension variable font."""
        excluded_glyphs = self._glyphs_from_fonts([feature_font_path])
        patched_wenyuan = self.patch_wenyuan(wenyuan_source, excluded_glyphs)
        feature_font = self.load_variable_font(feature_font_path)
        cn_extension = self.merge_fonts(
            feature_font, patched_wenyuan, "regular CN extension"
        )
        self.normalize_wght_axis(cn_extension)
        self.prune_stat(cn_extension)
        return cn_extension

    @staticmethod
    def _glyphs_from_fonts(paths: Iterable[Path]) -> set[str]:
        """Extract all glyph names from fonts."""
        glyphs: set[str] = set()
        for font_path in paths:
            font = TTFont(font_path)
            glyphs.update(font.getGlyphOrder())
            font.close()
        glyphs.discard(".notdef")
        return glyphs


def instantiate_wenyuan_var(
    f: str, base_dir: str, static_dir: str, italic_tmp_dir: str
):
    is_italic = "Italic" in f
    output_dir = italic_tmp_dir if is_italic else static_dir
    makedirs(output_dir, exist_ok=True)

    weight_map = {
        100: "Thin",
        210: "ExtraLight",
        320: "Light",
        400: "Regular",
        490: "Medium",
        570: "SemiBold",
        680: "Bold",
        800: "ExtraBold",
    }

    var_font = TTFont(joinPaths(base_dir, f))

    for weight, name in weight_map.items():
        print(f"Instantiating {name} {'Italic' if is_italic else ''}...")
        output_name = f"MapleMonoCN-{name}{'Italic' if is_italic else ''}.ttf".replace(
            "RegularItalic", "Italic"
        )
        output_path = joinPaths(output_dir, output_name)

        instance = instantiateVariableFont(var_font, {"wght": weight}, inplace=False)

        # Update font names
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

        instance.save(output_path)
        instance.close()

    var_font.close()


def flatten_italic_fonts(italic_tmp_dir: str, target_dir: str):
    if not Path(italic_tmp_dir).exists():
        return
    for f in listdir(italic_tmp_dir):
        shutil.move(joinPaths(italic_tmp_dir, f), joinPaths(target_dir, f))
    shutil.rmtree(italic_tmp_dir)


def optimize_wenyuan_base(f: str, base_dir: str):
    font_path = joinPaths(base_dir, f)
    print(f"✨ Optimize {font_path}")
    run(f"ftcli font del-table -t kern -t GPOS {font_path}", log=True)


def update_dir_hash(dir: str):
    run(f"ftcli name del-mac-names -r {dir}")
    with open(f"{dir}.sha256", "w") as f:
        f.write(get_directory_hash(dir))
        f.flush()
    print(f"#️⃣ Update {dir}.sha256")


def cn_wenyuan(cn_root: str, regenerate_vf: bool = True):
    print("🔨 Building CN WenYuan extension fonts...")

    processor = WenYuanProcessor()
    feature_font_path = Path("source/MapleMono-CN-feature-VF.ttf")
    wenyuan_source = Path("source/cn/WenYuanRoundedSCVF.ttf")

    var_output = joinPaths(cn_root, "MapleMono-CN-Extension-VF.ttf")
    var_italic_output = joinPaths(cn_root, "MapleMono-CN-Extension-Italic-VF.ttf")

    if (
        regenerate_vf
        or not Path(var_output).exists()
        or not Path(var_italic_output).exists()
    ):
        cn_extension = processor.build_cn_base_font(feature_font_path, wenyuan_source)
        italic_cn_extension = processor.make_italic(
            cn_extension, processor.config.DEFAULT_ITALIC_ANGLE
        )

        print(f"💾 Save variable fonts to {cn_root}")
        cn_extension.save(var_output)
        italic_cn_extension.save(var_italic_output)
        cn_extension.close()
        italic_cn_extension.close()
    else:
        print(f"♻️  Reusing existing variable fonts from {cn_root}")

    static_dir = joinPaths(cn_root, "static-wenyuan")
    italic_tmp_dir = joinPaths(static_dir, "italic")
    makedirs(static_dir, exist_ok=True)

    var_font_names = [
        "MapleMono-CN-Extension-VF.ttf",
        "MapleMono-CN-Extension-Italic-VF.ttf",
    ]

    print("📐 Instantiating static fonts...")
    for font_name in var_font_names:
        instantiate_wenyuan_var(
            font_name,
            base_dir=cn_root,
            static_dir=static_dir,
            italic_tmp_dir=italic_tmp_dir,
        )

    flatten_italic_fonts(italic_tmp_dir, static_dir)

    print("🗜️  Optimizing static fonts...")
    for f in listdir(static_dir):
        optimize_wenyuan_base(f, static_dir)

    update_dir_hash(static_dir)

    print("✅ CN WenYuan rebuild complete.")

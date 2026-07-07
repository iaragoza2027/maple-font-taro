from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._m_e_t_a import table__m_e_t_a

from source.py.build.config import ResolvedBuildConfig
from source.py.build.resolver import RuntimeBuildPlan
from source.py.cjk.presets import get_preset
from source.py.transform import change_glyph_width_or_scale
from source.py.utils import (
    adjust_line_height,
    parse_style_name,
    remove_target_glyph,
    update_font_names,
    verify_glyph_width,
)


def check_ftcli() -> None:
    package_name_v1 = "foundryToolsCLI"
    package_spec_v1 = importlib.util.find_spec(package_name_v1)
    package_name_v2 = "foundrytools_cli"
    package_spec_v2 = importlib.util.find_spec(package_name_v2)

    if not package_spec_v1 and not package_spec_v2:
        print(
            "❗ foundrytools-cli is not found. Please run `pip install foundrytools-cli`"
        )
        exit(1)

    try:
        installed_package = importlib.import_module(
            package_name_v2 if package_spec_v2 else package_name_v1
        )
        version = getattr(installed_package, "__version__", None)
        if version and version < "2":
            print(
                f"❗ foundrytools-cli version {version} is too old. Please run `pip install --upgrade foundrytools-cli`"
            )
            exit(1)
    except Exception as e:
        print(f"❗ Error checking foundrytools-cli version: {e}")
        exit(1)


def rename_glyph_name(
    font: TTFont,
    map: dict[str, str],
    post_extra_names: bool = True,
) -> None:
    def get_new_name_from_map(old_name: str, mapping: dict[str, str]) -> str | None:
        new_name = mapping.get(old_name)
        if not new_name:
            parts = re.split(r"[\._]", old_name, maxsplit=2)
            name = mapping.get(parts[0])
            if name:
                new_name = name + old_name[len(parts[0]) :]
        return new_name

    print("Rename glyph names")
    glyph_names = font.getGlyphOrder()
    extra_names = font["post"].extraNames  # type: ignore
    modified = False
    merged_map = {
        **map,
        **{
            "uni2047.liga": "question_question.liga",
            "uni2047.liga.cv62": "question_question.liga.cv62",
            "dotlessi": "idotless",
            "f_f": "f_f.liga",
            "tag_uni061C.liga": "tag_mark.liga",
            "tag_u1F5C8.liga": "tag_note.liga",
            "tag_uni26A0.liga": "tag_warning.liga",
            "uni266F_start.bg": "sharp_start.bg",
            "uni266F_end.bg": "sharp_end.bg",
        },
    }

    for index, _ in enumerate(glyph_names):
        old_name = str(glyph_names[index])
        new_name = get_new_name_from_map(old_name, merged_map)
        if not new_name or new_name == old_name:
            continue

        glyph_names[index] = new_name  # type: ignore
        modified = True

        if post_extra_names and old_name in extra_names:
            extra_names[extra_names.index(old_name)] = new_name

    if modified:
        font.setGlyphOrder(glyph_names)


def get_unique_identifier(
    font_config: ResolvedBuildConfig,
    postscript_name: str,
    narrow: bool = False,
    variable: bool = False,
) -> str:
    suffix = ""

    if variable:
        suffix += "Variable;"

    if "NF" in postscript_name:
        nf_ver = font_config.nerd_font.version
        suffix += f"NF{nf_ver};"

    if "CN" in postscript_name and narrow:
        suffix += "Narrow;"

    suffix += font_config.freeze_config_str

    beta_str = f"-{font_config.beta}" if font_config.beta else ""
    return f"{font_config.version_str}{beta_str};SUBF;{postscript_name};2024;FL830;{suffix}"


def build_cjk_family_name(font_config: ResolvedBuildConfig, locale_suffix: str) -> str:
    return f"{font_config.family_name} {locale_suffix}"


def build_cjk_postscript_prefix(
    font_config: ResolvedBuildConfig, locale_suffix: str
) -> str:
    return f"{font_config.family_name_compact}-{locale_suffix}"


def apply_cjk_meta_table(
    font: TTFont, language_tag: str, code_page_range1: int
) -> None:
    font["OS/2"].ulCodePageRange1 = code_page_range1  # type: ignore
    meta = table__m_e_t_a("meta")
    meta.data = {
        "dlng": language_tag,
        "slng": language_tag,
    }
    font["meta"] = meta


def apply_cjk_names(
    font: TTFont,
    font_config: ResolvedBuildConfig,
    locale_suffix: str,
    style_compact: str,
    narrow: bool,
) -> str:
    style_with_prefix_space, style_in_2, style_in_17, is_skip_subfamily, _ = (
        parse_style_name(style_name_compact=style_compact)
    )
    family_name = build_cjk_family_name(font_config, locale_suffix)
    postscript_prefix = build_cjk_postscript_prefix(font_config, locale_suffix)
    postscript_name = f"{postscript_prefix}-{style_compact}"
    update_font_names(
        font=font,
        family_name=f"{family_name}{style_with_prefix_space}",
        style_name=style_in_2,
        full_name=f"{family_name} {style_in_17}",
        version_str=font_config.version_str,
        postscript_name=postscript_name,
        unique_identifier=get_unique_identifier(
            font_config=font_config,
            postscript_name=postscript_name,
            narrow=narrow,
        ),
        is_skip_subfamily=is_skip_subfamily,
        preferred_family_name=family_name,
        preferred_style_name=style_in_17,
    )
    return postscript_name


def apply_cjk_metrics(font: TTFont, font_config: ResolvedBuildConfig) -> None:
    font["OS/2"].xAvgCharWidth = font_config.get_target_width()  # type: ignore
    adjust_line_height(font, font_config.line_height, font_config.vertical_metric)


def apply_cjk_width_transform(
    font: TTFont,
    font_config: ResolvedBuildConfig,
    locale_config,
) -> bool:
    target_width = font_config.glyph_width_cn_narrow if locale_config.narrow else None
    scale_factor: tuple[float, float] | None = (
        locale_config.scale_factor if locale_config.scale_factor != (1.0, 1.0) else None
    )
    special_scale_names = [
        "ellipsis.full",
        "quoteleft.full",
        "quoteright.full",
        "quotedblleft.full",
        "quotedblright.full",
    ]

    if target_width or scale_factor:
        match_width = 2 * font_config.glyph_width
        if target_width and font_config.get_width_name() != "slim":
            font["post"].isFixedPitch = False  # type: ignore
            font["OS/2"].panose.bProportion = 0  # type: ignore
            font["OS/2"].panose.bSpacing = 0  # type: ignore
            font["hhea"].advanceWidthMax = target_width  # type: ignore
            print(
                "Changed CJK glyph width, mark font file as not monospaced and skip checking glyph width"
            )
        else:
            target_width = match_width

        if scale_factor:
            print(f"Scale CJK glyphs to ({scale_factor[0]}x, {scale_factor[1]}x)")
        else:
            scale_factor = (1.0, 1.0)

        change_glyph_width_or_scale(
            font=font,
            match_width=match_width,
            target_width=target_width,
            scale_factor=scale_factor,
            special_names=special_scale_names,
        )
        return bool(target_width and font_config.get_width_name() != "slim")

    if font_config.get_width_name():
        change_glyph_width_or_scale(
            font=font,
            match_width=2 * font_config.glyph_width,
            target_width=2 * font_config.get_target_width(),
            scale_factor=(1.0, 1.0),
            special_names=special_scale_names,
        )
    return False


def verify_cjk_widths(
    font: TTFont,
    font_config: ResolvedBuildConfig,
    file_name: str,
    skip_verify: bool,
) -> None:
    if skip_verify:
        return
    verify_glyph_width(
        font=font,
        expect_widths=font_config.get_valid_glyph_width_list(True),
        file_name=file_name,
    )


def postprocess_cjk_extended_static_font(
    font: TTFont,
    locale: str,
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
    style_compact: str,
) -> str:
    locale_config = font_config.cjk.locales[locale]
    preset_spec = get_preset(locale)
    remove_target_glyph(font, ".1")
    postscript_name = apply_cjk_names(
        font,
        font_config,
        preset_spec.family_suffix,
        style_compact,
        locale_config.narrow,
    )
    skip_verify = apply_cjk_width_transform(font, font_config, locale_config)
    if locale_config.fix_meta_table:
        apply_cjk_meta_table(
            font,
            preset_spec.meta_languages,
            preset_spec.code_page_range1,
        )
    apply_cjk_metrics(font, font_config)
    font_config.patch_font_feature(
        font=font,
        issue_fea_dir=build_option.output_dir,
        is_italic="Italic" in style_compact,
        is_cn=True,
        is_variable=False,
        is_hinted=False,
        fea_path=build_option.feature_file_path("Italic" in style_compact, True),
    )
    verify_cjk_widths(font, font_config, postscript_name, skip_verify)
    return postscript_name


def get_cached_cjk_static_dir(locale: str) -> Path:
    return Path("source/cjk") / locale / "static"


def get_static_style_name(font_path: Path, static_file_prefix: str) -> str | None:
    prefix = f"{static_file_prefix}-"
    if not font_path.name.startswith(prefix) or font_path.suffix.lower() != ".ttf":
        return None
    return font_path.stem.removeprefix(prefix)


def get_core_static_font_styles(
    base_dir: str | Path,
    family_name_compact: str,
    target_styles: list[str] | None,
) -> list[tuple[str, Path]]:
    prefix = f"{family_name_compact}-"
    styles: list[tuple[str, Path]] = []
    for font_path in sorted(Path(base_dir).glob(f"{prefix}*.ttf")):
        style_compact = font_path.stem.removeprefix(prefix)
        if target_styles and style_compact not in target_styles:
            continue
        styles.append((style_compact, font_path))
    return styles

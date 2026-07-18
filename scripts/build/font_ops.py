from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import cast

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._m_e_t_a import table__m_e_t_a

from scripts.build.config import (
    CJKCommonBuildOptions,
    ResolvedBuildConfig,
    ResolvedCJKBuildEntry,
)
from scripts.build.errors import BuildDependencyError
from scripts.build.resolver import BuildRuntimeContext
from scripts.font.types import HheaTable, OS2Table, PostTable
from scripts.font.transform import change_glyph_width_or_scale
from scripts.feature.apply import patch_font_feature
from scripts.font.operations import (
    adjust_line_height,
    parse_style_name,
    remove_target_glyph,
    update_font_names,
    verify_glyph_width,
)


def parse_major_version(version: str) -> int | None:
    try:
        return int(version.split(".", 1)[0])
    except (TypeError, ValueError):
        return None


def check_ftcli() -> None:
    package_name_v1 = "foundryToolsCLI"
    package_spec_v1 = importlib.util.find_spec(package_name_v1)
    package_name_v2 = "foundrytools_cli"
    package_spec_v2 = importlib.util.find_spec(package_name_v2)

    if not package_spec_v1 and not package_spec_v2:
        raise BuildDependencyError(
            "foundrytools-cli is not found. Please run `pip install foundrytools-cli`"
        )

    try:
        installed_package = importlib.import_module(
            package_name_v2 if package_spec_v2 else package_name_v1
        )
        version = getattr(installed_package, "__version__", None)
        major_version = parse_major_version(version) if version else None
        if major_version is not None and major_version < 2:
            raise BuildDependencyError(
                f"foundrytools-cli version {version} is too old. Please run `pip install --upgrade foundrytools-cli`"
            )
    except Exception as e:
        if isinstance(e, BuildDependencyError):
            raise
        raise BuildDependencyError(
            f"Error checking foundrytools-cli version: {e}"
        ) from e


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
    font["OS/2"].ulCodePageRange1 = code_page_range1
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


def apply_cjk_metrics(
    font: TTFont,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
) -> None:
    cast(OS2Table, font["OS/2"]).xAvgCharWidth = font_config.get_target_width()
    adjust_line_height(
        font, font_config.line_height, runtime_context.resolved_vertical_metric
    )


def apply_cjk_width_transform(
    font: TTFont,
    font_config: ResolvedBuildConfig,
    common_options: CJKCommonBuildOptions,
) -> bool:
    target_width = font_config.glyph_width_cn_narrow if common_options.narrow else None
    scale_factor: tuple[float, float] | None = (
        common_options.scale_factor
        if common_options.scale_factor != (1.0, 1.0)
        else None
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
            cast(PostTable, font["post"]).isFixedPitch = False
            os2 = cast(OS2Table, font["OS/2"])
            os2.panose.bProportion = 0
            os2.panose.bSpacing = 0
            cast(HheaTable, font["hhea"]).advanceWidthMax = target_width
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
    cjk_narrow: bool,
) -> None:
    if skip_verify:
        return
    verify_glyph_width(
        font=font,
        expect_widths=font_config.get_valid_glyph_width_list(True, cjk_narrow),
        file_name=file_name,
    )


def postprocess_cjk_extended_static_font(
    font: TTFont,
    entry: ResolvedCJKBuildEntry,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    style_compact: str,
    locale_suffix: str | None = None,
) -> str:
    remove_target_glyph(font, ".1")
    postscript_name = apply_cjk_names(
        font,
        font_config,
        locale_suffix or entry.locale_name,
        style_compact,
        entry.common_options.narrow,
    )
    skip_verify = apply_cjk_width_transform(font, font_config, entry.common_options)
    if entry.is_builtin and entry.common_options.fix_meta_table and entry.preset_spec:
        apply_cjk_meta_table(
            font,
            entry.preset_spec.meta_languages,
            entry.preset_spec.code_page_range1,
        )
    apply_cjk_metrics(font, font_config, runtime_context)
    patch_font_feature(
        config=font_config,
        font=font,
        issue_fea_dir=runtime_context.output_dir,
        is_italic="Italic" in style_compact,
        is_cn=True,
        is_variable=False,
        is_hinted=False,
        fea_path=runtime_context.feature_file_path("Italic" in style_compact, True),
    )
    verify_cjk_widths(
        font,
        font_config,
        postscript_name,
        skip_verify,
        entry.common_options.narrow,
    )
    return postscript_name


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

#!/usr/bin/env python3
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import time
from functools import partial
from os import getcwd, listdir, makedirs, path, remove
from typing import Callable
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._m_e_t_a import table__m_e_t_a
from fontTools.varLib.instancer import instantiateVariableFont
from ttfautohint import StemWidthMode, ttfautohint
from source.py.transform import change_glyph_width_or_scale, smart_change_width
from source.py.build.config import ResolvedBuildConfig
from source.py.build.paths import merged_variable_name, static_output_dir, variable_output_dir
from source.py.build.resolver import BuildConfigResolver, RuntimeBuildPlan
from source.py.cjk.builder import (
    build_cjk_fonts,
    create_font_executor,
    feature_weight_instances,
    get_static_worker_font,
)
from source.py.cjk.presets import build_preset_config, get_preset
from source.py.cjk.vf import load_font_eager, merge_vf
from source.py.utils import (
    add_gasp,
    add_ital_axis_to_stat,
    adjust_line_height,
    alias_codepoints,
    parse_style_name,
    patch_instance,
    update_font_names,
    verify_glyph_width,
    archive_fonts,
    is_ci,
    match_unicode_names,
    run,
    joinPaths,
    merge_ttfonts,
    remove_target_glyph,
)


FONT_VERSION = "v7.9"
# =========================================================================================


def check_ftcli():
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


# =========================================================================================

# def fix_cn_cv(font: TTFont):
#     gsub_table = font["GSUB"].table
#     config = {
#         "cv96": ["quoteleft", "quoteright", "quotedblleft", "quotedblright"],
#         "cv97": ["ellipsis"],
#         "cv98": ["emdash"],
#     }

#     for feature_record in gsub_table.FeatureList.FeatureRecord:
#         if feature_record.FeatureTag in config:
#             sub_table = gsub_table.LookupList.Lookup[
#                 feature_record.Feature.LookupListIndex[0]
#             ].SubTable[0]
#             sub_table.mapping = {
#                 value: f"{value}.full" for value in config[feature_record.FeatureTag]
#             }


# def remove_locl(font: TTFont):
#     gsub = font["GSUB"]
#     features_to_remove = []

#     for feature in gsub.table.FeatureList.FeatureRecord:
#         feature_tag = feature.FeatureTag

#         if feature_tag == "locl":
#             features_to_remove.append(feature)

#     for feature in features_to_remove:
#         gsub.table.FeatureList.FeatureRecord.remove(feature)


def rename_glyph_name(
    font: TTFont,
    map: dict[str, str],
    post_extra_names: bool = True,
):
    def get_new_name_from_map(old_name: str, map: dict[str, str]):
        new_name = map.get(old_name)
        if not new_name:
            arr = re.split(r"[\._]", old_name, maxsplit=2)
            name = map.get(arr[0])
            if name:
                new_name = name + old_name[len(arr[0]) :]
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

    for i, _ in enumerate(glyph_names):
        old_name = str(glyph_names[i])

        new_name = get_new_name_from_map(old_name, merged_map)
        if not new_name or new_name == old_name:
            continue

        # print(f"[Rename] {old_name} -> {new_name}")
        glyph_names[i] = new_name  # type: ignore
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


def build_mono(
    f: str, font_config: ResolvedBuildConfig, build_option: RuntimeBuildPlan
):
    print(f"👉 Minimal version for {f}")
    source_path = joinPaths(build_option.output_ttf, f)

    run(f"ftcli fix italic-angle {source_path}")
    run(f"ftcli fix monospace {source_path}")
    run(f"ftcli name strip-names {source_path}")
    run(f"ftcli font correct-contours {source_path}")
    run(f"ftcli ttf dehint {source_path}")
    run(f"ftcli fix transformed-components {source_path}")

    font = TTFont(source_path)

    style_compact = f.split("-")[-1].split(".")[0]

    style_with_prefix_space, style_in_2, style_in_17, is_skip_subfamily, is_italic = (
        parse_style_name(
            style_name_compact=style_compact,
        )
    )

    postscript_name = f"{font_config.family_name_compact}-{style_compact}"

    update_font_names(
        font=font,
        family_name=font_config.family_name + style_with_prefix_space,
        style_name=style_in_2,
        full_name=f"{font_config.family_name} {style_in_17}",
        version_str=font_config.version_str,
        postscript_name=postscript_name,
        unique_identifier=get_unique_identifier(
            font_config=font_config,
            postscript_name=postscript_name,
        ),
        is_skip_subfamily=is_skip_subfamily,
        preferred_family_name=font_config.family_name,
        preferred_style_name=style_in_17,
    )

    # https://github.com/ftCLI/FoundryTools-CLI/issues/166#issuecomment-2095433585
    if style_with_prefix_space == " Thin":
        font["OS/2"].usWeightClass = 250  # type: ignore
    elif style_with_prefix_space == " ExtraLight":
        font["OS/2"].usWeightClass = 275  # type: ignore

    font_config.patch_font_feature(
        font=font,
        issue_fea_dir=build_option.output_dir,
        is_italic=is_italic,
        is_cn=False,
        is_variable=False,
        is_hinted=False,
        fea_path=build_option.feature_file_path(is_italic),
    )

    verify_glyph_width(
        font=font,
        expect_widths=font_config.get_valid_glyph_width_list(),
        file_name=postscript_name,
    )

    remove(source_path)
    target_path = joinPaths(build_option.output_ttf, f"{postscript_name}.ttf")
    font.save(target_path)

    if font_config.wants_format("woff2") and not font_config.debug:
        print(f"Convert {postscript_name}.ttf to WOFF2")
        run(
            f"ftcli converter ft2wf {target_path} -out {build_option.output_woff2} -f woff2"
        )

    if font_config.wants_format("otf") and not font_config.debug:
        _otf_path = joinPaths(
            build_option.output_otf, path.basename(target_path).replace(".ttf", ".otf")
        )
        print(f"Convert {postscript_name}.ttf to OTF")
        run(f"ftcli converter ttf2otf {target_path} -out {build_option.output_otf}")
        print(f"Optimize {postscript_name}.otf")
        run(f"ftcli font correct-contours {_otf_path}")
        run(f"ftcli cff set-names --version {font_config.version} {_otf_path}")


def build_mono_autohint(
    f: str, font_config: ResolvedBuildConfig, build_option: RuntimeBuildPlan
):
    style_compact = f.split("-")[-1].split(".")[0]
    postscript_name = f"{font_config.family_name_compact}-{style_compact}"
    print(f"👉 Auto hint {postscript_name}.ttf")

    source_path = joinPaths(build_option.output_ttf, f)
    font = TTFont(source_path)
    is_italic = "Italic" in style_compact
    font_config.patch_font_feature(
        font=font,
        issue_fea_dir=build_option.output_dir,
        is_italic=is_italic,
        is_cn=False,
        is_variable=False,
        is_hinted=True,
        fea_path=build_option.feature_file_path(is_italic),
    )

    # Ensure flags to respect hint info
    font["head"].flags = font["head"].flags | 1 << 2 | 1 << 3  # type: ignore

    param: dict | None = font_config.ttfautohint_param

    buf = BytesIO()
    font.save(buf)
    font.close()

    # https://freetype.org/ttfautohint/doc/ttfautohint.html#options
    # Also see `ttfautohint.options.USER_OPTIONS`
    options = {
        "in_buffer": buf.getvalue(),
        "reference_file": joinPaths(
            build_option.output_ttf, f"{font_config.family_name_compact}-Regular.ttf"
        ),
        "out_file": joinPaths(build_option.output_ttf_hinted, f"{postscript_name}.ttf"),
        "windows_compatibility": True,
    }

    def parse_stem_width_mode(mode: str) -> StemWidthMode:
        if mode == "natural":
            return StemWidthMode.NATURAL
        elif mode == "strong":
            return StemWidthMode.STRONG
        elif mode == "quantized":
            return StemWidthMode.QUANTIZED
        else:
            raise ValueError(f"Unknown stem width mode: {mode}")

    if param:
        options.update(param)
        if "stem_width_mode" in param:
            del options["stem_width_mode"]
            if "gray" in param:
                options["gray_stem_width_mode"] = parse_stem_width_mode(
                    param["stem_width_mode"]["gray"]
                )
            if "gdi_cleartype" in param:
                options["gdi_cleartype_stem_width_mode"] = parse_stem_width_mode(
                    param["stem_width_mode"]["gdi_cleartype"]
                )
            if "dw_cleartype" in param:
                options["dw_cleartype_stem_width_mode"] = parse_stem_width_mode(
                    param["stem_width_mode"]["dw_cleartype"]
                )

    ttfautohint(**options)


def build_nf_by_prebuild_nerd_font(
    font_basename: str,
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
) -> TTFont:
    suffix = font_config.get_nf_suffix()
    if suffix:
        suffix = "-" + suffix

    nf_base_font_path = f"{build_option.src_dir}/MapleMono-NF-Base{suffix}.ttf"
    tmp_target_path = None
    if font_config.get_width_name():
        tmp_font = TTFont(nf_base_font_path)
        smart_change_width(
            font=tmp_font,
            target_width=font_config.get_target_width(),
            original_ref_width=font_config.glyph_width,
            also_scale_y=True,
        )
        tmp_target_path = f"{build_option.output_dir}/NF-Base-{font_basename}"
        tmp_font.save(tmp_target_path)

    result = merge_ttfonts(
        base_font_path=joinPaths(build_option.ttf_base_dir, font_basename),
        extra_font_path=tmp_target_path or nf_base_font_path,
    )

    if tmp_target_path is not None:
        remove(tmp_target_path)

    return result


def build_nf_by_font_patcher(
    font_basename: str,
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
) -> TTFont:
    """
    full args: https://github.com/ryanoasis/nerd-fonts?tab=readme-ov-file#font-patcher
    """
    _nf_args = [
        build_option.font_forge_bin,
        "FontPatcher/font-patcher",
        "-l",
        "--careful",
        "--outputdir",
        build_option.output_nf,
    ] + font_config.nerd_font.glyphs

    if font_config.nerd_font.propo:
        _nf_args += ["--variable-width-glyphs"]
    elif font_config.nerd_font.mono:
        _nf_args += ["--mono"]

    extra_args = font_config.nerd_font.extra_args
    _nf_args += extra_args

    run(_nf_args + [joinPaths(build_option.ttf_base_dir, font_basename)])

    nf_file_name = "NerdFont" + font_config.get_nf_suffix()

    _path = joinPaths(
        build_option.output_nf, font_basename.replace("-", f"{nf_file_name}-")
    )
    font = TTFont(_path)
    remove(_path)

    # Check if the glyph 'nonmarkingreturn' exists in the font
    extra_name = "nonmarkingreturn"
    if extra_name in font.getGlyphNames():
        font["hmtx"][extra_name] = (600, 0)  # type: ignore
    return font


def build_nf(
    f: str,
    get_ttfont: Callable[[str, ResolvedBuildConfig, RuntimeBuildPlan], TTFont],
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
):
    print(f"👉 NerdFont{font_config.get_nf_suffix()} version for {f}")
    nf_font = get_ttfont(f, font_config, build_option)

    # format font name
    style_compact_nf = f.split("-")[-1].split(".")[0]

    style_nf_with_prefix_space, style_in_2, style_in_17, is_skip_sufamily, _ = (
        parse_style_name(
            style_name_compact=style_compact_nf,
        )
    )

    nf_sym = f"NF{font_config.get_nf_suffix()}"
    postscript_name = f"{font_config.family_name_compact}-{nf_sym}-{style_compact_nf}"

    update_font_names(
        font=nf_font,
        family_name=f"{font_config.family_name} {nf_sym}{style_nf_with_prefix_space}",
        style_name=style_in_2,
        full_name=f"{font_config.family_name} {nf_sym} {style_in_17}",
        version_str=font_config.version_str,
        postscript_name=postscript_name,
        unique_identifier=get_unique_identifier(
            font_config=font_config,
            postscript_name=postscript_name,
        ),
        is_skip_subfamily=is_skip_sufamily,
        preferred_family_name=f"{font_config.family_name} {nf_sym}",
        preferred_style_name=style_in_17,
    )

    if font_config.line_height != 1:
        adjust_line_height(
            nf_font, font_config.line_height, font_config.vertical_metric
        )

    if not (
        build_option.resolve_font_patcher_usage(font_config)
        or font_config.get_nf_suffix() == "Propo"
    ):
        verify_glyph_width(
            font=nf_font,
            expect_widths=font_config.get_valid_glyph_width_list(),
            file_name=postscript_name,
        )

    target_path = joinPaths(
        build_option.output_nf,
        f"{postscript_name}.ttf",
    )
    nf_font.save(target_path)
    nf_font.close()


def run_build(
    pool_size: int, fn: Callable, dir: str, target_styles: list[str] | None = None
):
    """Run build tasks in parallel using ProcessPoolExecutor."""
    if target_styles:
        files = []
        for f in listdir(dir):
            if f.split("-")[-1][:-4] in target_styles:
                files.append(f)
            elif "NF" not in f:
                remove(joinPaths(dir, f))
    else:
        files = listdir(dir)

    if pool_size <= 1:
        for f in files:
            fn(f)
        return

    first_exc: Exception | None = None
    with ProcessPoolExecutor(max_workers=pool_size) as executor:
        futures = {executor.submit(fn, f): f for f in files}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                # Optionally, cancel other futures if needed
                for f in futures:
                    if not f.done():
                        f.cancel()
                if not first_exc:
                    first_exc = e
                    raise e


@dataclass(frozen=True)
class MapleStaticInstanceJob:
    input_path: str
    output_path: str
    coordinate: float


def instantiate_maple_static_font_file(
    input_path: str,
    output_path: str,
    coordinate: float,
) -> None:
    print(f"Instantiating {path.basename(output_path)}...")
    var_font = get_static_worker_font(input_path)
    instance = instantiateVariableFont(
        var_font,
        {"wght": coordinate},
        inplace=False,
        static=True,
        downgradeCFF2="CFF2" in var_font,
    )
    try:
        instance.save(output_path)
    finally:
        instance.close()


def instantiate_maple_static_font_job(job: MapleStaticInstanceJob) -> None:
    instantiate_maple_static_font_file(
        job.input_path,
        job.output_path,
        job.coordinate,
    )


def instantiate_base_static_fonts(
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
) -> None:
    print("Instantiate TTF")
    jobs: list[MapleStaticInstanceJob] = []
    regular_input_path = joinPaths(
        build_option.output_variable,
        f"{font_config.family_name_compact}[wght].ttf",
    )
    regular_var_font = load_font_eager(regular_input_path)
    try:
        instances = feature_weight_instances(regular_var_font)
    finally:
        regular_var_font.close()

    for is_italic in (False, True):
        input_path = joinPaths(
            build_option.output_variable,
            f"{font_config.family_name_compact}{'-Italic' if is_italic else ''}[wght].ttf",
        )
        for instance in instances:
            base_name = instance.name.replace(" Italic", "").replace(" ", "")
            style_compact = (
                f"{base_name}Italic" if is_italic else base_name
            ).replace("RegularItalic", "Italic")
            output_path = joinPaths(
                build_option.output_ttf,
                f"{font_config.family_name_compact}-{style_compact}.ttf",
            )
            jobs.append(
                MapleStaticInstanceJob(
                    input_path=input_path,
                    output_path=output_path,
                    coordinate=instance.coordinate,
                )
            )

    executor = create_font_executor()
    try:
        futures = [executor.submit(instantiate_maple_static_font_job, job) for job in jobs]
        for future in futures:
            future.result()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def build_variable_fonts(
    font_config: ResolvedBuildConfig, build_option: RuntimeBuildPlan
):
    """Build variable font versions from source files."""
    input_files = [
        joinPaths(build_option.src_dir, "MapleMono-Italic[wght]-VF.ttf"),
        joinPaths(build_option.src_dir, "MapleMono[wght]-VF.ttf"),
    ]
    for input_file in input_files:
        font = TTFont(input_file)
        basename = path.basename(input_file)
        print(f"👉 Variable version for {basename}")

        # fix auto rename by FontLab
        rename_glyph_name(
            font=font,
            map=match_unicode_names(
                input_file.replace(".ttf", ".glyphs").replace("-VF", "")
            ),
        )

        alias_codepoints(font=font)

        if font_config.get_width_name():
            smart_change_width(
                font=font,
                target_width=font_config.get_target_width(),
                original_ref_width=font_config.glyph_width,
            )

        is_italic = "Italic" in input_file

        font_config.patch_font_feature(
            font=font,
            issue_fea_dir=build_option.output_dir,
            is_italic=is_italic,
            is_cn=False,
            is_variable=True,
            is_hinted=False,
            fea_path=build_option.feature_file_path(is_italic),
        )

        style_name = "Italic" if is_italic else "Regular"
        postscript_name = f"{font_config.family_name_compact}-{style_name}"
        update_font_names(
            font=font,
            family_name=font_config.family_name,
            style_name=style_name,
            full_name=f"{font_config.family_name} {style_name}",
            version_str=font_config.version_str,
            postscript_name=postscript_name,
            unique_identifier=get_unique_identifier(
                font_config=font_config,
                postscript_name=postscript_name,
                variable=True,
            ),
            is_skip_subfamily=True,
        )

        if is_italic:
            add_ital_axis_to_stat(font)

        patch_instance(font, font_config.weight_mapping)

        if font_config.line_height != 1:
            calculated_metric = (font["hhea"].ascender, font["hhea"].descender)  # type: ignore
            if calculated_metric != font_config.vertical_metric:
                font_config.vertical_metric = calculated_metric

            adjust_line_height(font, font_config.line_height, calculated_metric)

        verify_glyph_width(
            font=font,
            expect_widths=font_config.get_valid_glyph_width_list(),
            file_name=basename,
        )

        add_gasp(font)

        file_name = font_config.family_name_compact
        if is_italic:
            file_name += "-Italic"

        font.save(joinPaths(build_option.output_variable, f"{file_name}[wght].ttf"))

    print("\n✨ Instantiate and optimize fonts...\n")

    print("Check and optimize variable fonts")

    # Italic angle is correct here.
    # run(f"ftcli fix italic-angle {build_option.output_variable}")

    run(f"ftcli fix monospace {build_option.output_variable}")
    # run(f"ftcli fix vertical-metrics {build_option.output_variable}")
    # run(f"ftcli name del-mac-names -r {build_option.output_variable}")

    instantiate_base_static_fonts(font_config, build_option)


def build_cjk_family_name(
    font_config: ResolvedBuildConfig, locale_suffix: str
) -> str:
    return f"{font_config.family_name} {locale_suffix}"


def build_cjk_postscript_prefix(
    font_config: ResolvedBuildConfig, locale_suffix: str
) -> str:
    return f"{font_config.family_name_compact}{locale_suffix}"


def apply_cjk_meta_table(font: TTFont, language_tag: str, code_page_range1: int) -> None:
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
        locale_config.scale_factor
        if locale_config.scale_factor != (1.0, 1.0)
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


def ensure_cjk_variable_fonts(
    locale: str,
    locale_config,
    preset_spec,
    preset_config,
) -> tuple[Path, Path] | None:
    regular_path = preset_config.output.dir / preset_config.output.regular_variable
    italic_path = preset_config.output.dir / preset_config.output.italic_variable

    if (
        not locale_config.clean_cache
        and regular_path.exists()
        and italic_path.exists()
    ):
        print(
            f"♻️ Reuse cached {preset_spec.family_suffix} variable fonts: "
            f"{regular_path.name}, {italic_path.name}"
        )
        return regular_path, italic_path

    try:
        build_cjk_fonts(preset_config, vf_only=True)
    except FileNotFoundError as error:
        print(f"⚠️ Skip {preset_spec.family_suffix} extended fonts: {error}")
        return None

    if not regular_path.exists() or not italic_path.exists():
        print(
            f"⚠️ Skip {preset_spec.family_suffix} extended fonts: "
            "variable font outputs were not generated"
        )
        return None
    return regular_path, italic_path


def build_cjk_extended_variable_fonts(
    locale: str,
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
    output_dir: Path,
) -> tuple[Path, Path] | None:
    locale_config = font_config.cjk.locales[locale]
    preset_spec = get_preset(locale)
    preset_config = build_preset_config(locale)
    base_variable_paths = ensure_cjk_variable_fonts(
        locale,
        locale_config,
        preset_spec,
        preset_config,
    )
    if base_variable_paths is None:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    core_pairs = (
        (False, Path(build_option.output_variable) / f"{font_config.family_name_compact}[wght].ttf"),
        (True, Path(build_option.output_variable) / f"{font_config.family_name_compact}-Italic[wght].ttf"),
    )
    base_pairs = (
        (False, base_variable_paths[0]),
        (True, base_variable_paths[1]),
    )
    output_paths: list[Path] = []

    for (is_italic, base_path), (_, extra_path) in zip(core_pairs, base_pairs):
        if not base_path.exists():
            print(f"⚠️ Core variable font not found: {base_path}")
            return None
        if not extra_path.exists():
            print(f"⚠️ CJK variable font not found: {extra_path}")
            return None

        merged_font, added_glyphs, added_codepoints = merge_vf(base_path, extra_path)
        try:
            locale_suffix = preset_spec.family_suffix
            family_name = build_cjk_family_name(font_config, locale_suffix)
            postscript_prefix = build_cjk_postscript_prefix(font_config, locale_suffix)
            postscript_name = postscript_prefix + ("-Italic" if is_italic else "")
            style_name = "Italic" if is_italic else "Regular"
            update_font_names(
                font=merged_font,
                family_name=family_name,
                style_name=style_name,
                full_name=f"{family_name} {style_name}",
                version_str=font_config.version_str,
                postscript_name=postscript_name,
                unique_identifier=get_unique_identifier(
                    font_config=font_config,
                    postscript_name=postscript_name,
                    narrow=locale_config.narrow,
                    variable=True,
                ),
                is_skip_subfamily=True,
            )
            if locale_config.fix_meta_table:
                apply_cjk_meta_table(
                    merged_font,
                    preset_spec.meta_languages,
                    preset_spec.code_page_range1,
                )
            output_path = output_dir / merged_variable_name(postscript_prefix, is_italic)
            print(
                f"👉 Merge {preset_spec.family_suffix} variable font: +{len(added_glyphs)} glyphs, +{added_codepoints} unicodes"
            )
            merged_font.save(output_path)
            print(f"✅ Saved merged variable font: {output_path}")
            output_paths.append(output_path)
        finally:
            merged_font.close()

    return output_paths[0], output_paths[1]


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


def instantiate_cjk_extended_static_fonts(
    locale: str,
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
    merged_paths: tuple[Path, Path],
    target_styles: list[str] | None,
) -> Path:
    locale_config = font_config.cjk.locales[locale]
    preset_spec = get_preset(locale)
    output_dir = static_output_dir(build_option.output_dir, locale)
    output_dir.mkdir(parents=True, exist_ok=True)

    for is_italic, merged_path in ((False, merged_paths[0]), (True, merged_paths[1])):
        var_font = load_font_eager(merged_path)
        try:
            instances = feature_weight_instances(var_font)
            for instance in instances:
                style_compact = (
                    f"{instance.name}Italic" if is_italic else instance.name
                ).replace("RegularItalic", "Italic")
                if target_styles and style_compact not in target_styles:
                    continue
                print(f"👉 Instantiate {preset_spec.family_suffix} static font: {style_compact}")
                static_font = instantiateVariableFont(
                    var_font,
                    {"wght": instance.coordinate},
                    inplace=False,
                    static=True,
                    downgradeCFF2="CFF2" in var_font,
                )
                try:
                    postscript_name = postprocess_cjk_extended_static_font(
                        static_font,
                        locale,
                        font_config,
                        build_option,
                        style_compact,
                    )
                    static_font.save(output_dir / f"{postscript_name}.ttf")
                finally:
                    static_font.close()
        finally:
            var_font.close()

    if locale_config.use_hinted:
        print(f"Auto hinting all {preset_spec.family_suffix} glyphs")
        run(f"ftcli ttf autohint {output_dir}")

    return output_dir


def build_cjk_extended_outputs(
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
    target_styles: list[str] | None,
) -> None:
    locales = font_config.get_selected_cjk_locales()
    if not locales:
        return

    persist_variable = font_config.cjk_output_format == "variable"
    temp_root = Path(build_option.output_dir) / ".cjk-temp"
    built_any = False
    for locale in locales:
        locale_output_dir = (
            variable_output_dir(build_option.output_dir, locale)
            if persist_variable
            else temp_root / locale.upper()
        )
        merged_paths = build_cjk_extended_variable_fonts(
            locale,
            font_config,
            build_option,
            locale_output_dir,
        )
        if merged_paths is None:
            continue
        built_any = True
        if persist_variable:
            continue
        instantiate_cjk_extended_static_fonts(
            locale,
            font_config,
            build_option,
            merged_paths,
            target_styles,
        )
        shutil.rmtree(locale_output_dir, ignore_errors=True)

    if not persist_variable:
        shutil.rmtree(temp_root, ignore_errors=True)
    build_option.is_cjk_built = built_any


def cleanup_unselected_base_formats(
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
) -> None:
    if font_config.wants_format("ttf"):
        return

    shutil.rmtree(build_option.output_ttf, ignore_errors=True)
    shutil.rmtree(build_option.output_ttf_hinted, ignore_errors=True)


def ensure_base_output_dirs(build_option: RuntimeBuildPlan) -> None:
    makedirs(build_option.output_dir, exist_ok=True)
    makedirs(build_option.output_variable, exist_ok=True)
    makedirs(build_option.output_ttf, exist_ok=True)
    makedirs(build_option.output_ttf_hinted, exist_ok=True)


def build_base_fonts(
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
    target_styles: list[str] | None,
):
    """Apply mono building and auto-hinting to static TTF fonts."""
    run_build(
        font_config.pool_size,
        partial(
            build_mono,
            font_config=font_config,
            build_option=build_option,
        ),
        build_option.output_ttf,
        target_styles,
    )

    run_build(
        font_config.pool_size,
        partial(
            build_mono_autohint,
            font_config=font_config,
            build_option=build_option,
        ),
        build_option.output_ttf,
        target_styles,
    )


def build_nerd_fonts(
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
    target_styles: list[str] | None,
):
    """Build Nerd Font variants."""
    if not font_config.nerd_font.enable:
        return

    makedirs(build_option.output_nf, exist_ok=True)
    use_font_patcher = build_option.resolve_font_patcher_usage(font_config)

    get_ttfont = (
        build_nf_by_font_patcher if use_font_patcher else build_nf_by_prebuild_nerd_font
    )

    _version = font_config.nerd_font.version
    print(
        f"\n🔧 Patch Nerd-Font v{_version} using {'Font Patcher' if use_font_patcher else 'prebuild base font'}...\n"
    )

    run_build(
        font_config.pool_size,
        partial(
            build_nf,
            get_ttfont=get_ttfont,
            font_config=font_config,
            build_option=build_option,
        ),
        build_option.ttf_base_dir,
        target_styles,
    )
    build_option.is_nf_built = True


# Now, refactor the main function to use these
def main(parsed_args, version: str | None = None):
    global FONT_VERSION

    check_ftcli()

    version_tag = version or FONT_VERSION
    if version:
        FONT_VERSION = version

    resolver = BuildConfigResolver(version_tag=version_tag)
    font_config = resolver.resolve(parsed_args)
    build_option = RuntimeBuildPlan.from_config(font_config)

    if parsed_args.dry:
        if is_ci():
            print(json.dumps(font_config.to_dict(), indent=4))
        else:
            print("resolved_config:", json.dumps(font_config.to_dict(), indent=4))
            print(
                "runtime_plan:",
                json.dumps(build_option.to_dict(font_config), indent=4),
            )
        return

    should_use_cache = font_config.cache
    target_styles = None
    if font_config.least_styles:
        target_styles = ["Regular", "Bold", "Italic", "BoldItalic"]
    elif font_config.debug:
        target_styles = ["Regular", "Italic"]

    if not should_use_cache:
        print("🧹 Clean cache...\n")
        shutil.rmtree(build_option.output_dir, ignore_errors=True)
        shutil.rmtree(build_option.output_woff2, ignore_errors=True)

    ensure_base_output_dirs(build_option)

    start_time = time.time()
    print(
        f"🚩 Start building {font_config.family_name} {font_config.version_str} ...\n"
    )

    # Build basic fonts if no cache
    if not should_use_cache or not build_option.has_cache:
        build_variable_fonts(font_config, build_option)
        build_base_fonts(font_config, build_option, target_styles)

    # Build variants
    build_nerd_fonts(font_config, build_option, target_styles)
    build_cjk_extended_outputs(font_config, build_option, target_styles)
    cleanup_unselected_base_formats(font_config, build_option)
    if font_config.use_cn_both:
        print(
            "⚠️ `--cn-both` is deprecated and not part of the locale-agnostic CJK-extended path. "
            "Only the generic `--cjk` output flow is generated."
        )

    # Write config
    with open(
        joinPaths(build_option.output_dir, "build-config.json"), "w", encoding="utf-8"
    ) as config_file:
        config_file.write(
            json.dumps(
                font_config.to_build_record(),
                indent=4,
            )
        )

    # Archive if requested
    if font_config.archive:
        print("\n🚀 archive files...\n")

        # archive fonts
        archive_dir_name = "archive"
        archive_dir = joinPaths(build_option.output_dir, archive_dir_name)
        makedirs(archive_dir, exist_ok=True)

        # archive fonts
        for f in listdir(build_option.output_dir):
            if f == archive_dir_name or f.endswith(".json"):
                continue

            suffix = ""
            if f in ["CN", "NF", "NF-CN"]:
                if not font_config.use_hinted:
                    suffix = "-unhinted"
            else:
                if should_use_cache:
                    continue

            sha256, zip_file_name_without_ext = archive_fonts(
                family_name_compact=font_config.family_name_compact,
                suffix=suffix,
                source_file_or_dir_path=joinPaths(build_option.output_dir, f),
                build_config_path=joinPaths(
                    build_option.output_dir, "build-config.json"
                ),
                target_parent_dir_path=archive_dir,
            )
            with open(
                joinPaths(archive_dir, f"{zip_file_name_without_ext}.sha256"),
                "w",
                encoding="utf-8",
            ) as hash_file:
                hash_file.write(sha256)

            print(f"👉 archive: {f}")

    # Finish
    if is_ci():
        return

    freeze_str = (
        font_config.freeze_config_str
        if font_config.freeze_config_str != ""
        else "default config"
    )
    end_time = time.time()
    date_time_fmt = time.strftime("%H:%M:%S", time.localtime(end_time))
    time_diff = end_time - start_time
    output = joinPaths(getcwd().replace("\\", "/"), build_option.output_dir)
    print(
        f"\n🏁 Build finished at {date_time_fmt}, cost {time_diff:.2f} s, family name is {font_config.family_name}, {freeze_str}\n   See your fonts in {output}"
    )


if __name__ == "__main__":
    from source.py.build.cli import main as cli_main

    cli_main()

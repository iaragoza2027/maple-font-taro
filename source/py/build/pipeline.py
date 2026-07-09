#!/usr/bin/env python3
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
import shutil
import time
from os import getcwd, listdir, makedirs, path, remove
from typing import Callable
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from ttfautohint import StemWidthMode, ttfautohint
from source.py.transform import smart_change_width
from source.py.build.config import ResolvedBuildConfig
from source.py.build.paths import (
    merged_variable_name,
    static_output_dir,
    variable_output_dir,
)
from source.py.build.resolver import BuildConfigResolver, RuntimeBuildPlan
from source.py.build.util import (
    apply_cjk_meta_table,
    build_cjk_family_name,
    build_cjk_postscript_prefix,
    check_ftcli,
    get_cached_cjk_static_dir,
    get_core_static_font_styles,
    get_static_style_name,
    get_unique_identifier,
    postprocess_cjk_extended_static_font,
    rename_glyph_name,
)
from source.py.cjk.builder import (
    build_cjk_fonts,
    create_font_executor,
    feature_weight_instances,
    get_static_worker_font,
)
from source.py.cjk.config import CJKBuildConfig
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
)


FONT_VERSION = "v7.9"
# =========================================================================================


@dataclass(frozen=True)
class MonoBuildJob:
    font_basename: str
    font_config: ResolvedBuildConfig
    build_option: RuntimeBuildPlan


@dataclass(frozen=True)
class MonoAutohintJob:
    font_basename: str
    font_config: ResolvedBuildConfig
    build_option: RuntimeBuildPlan


@dataclass(frozen=True)
class NerdFontBuildJob:
    font_basename: str
    use_font_patcher: bool
    font_config: ResolvedBuildConfig
    build_option: RuntimeBuildPlan


@dataclass(frozen=True)
class CJKStaticMergeJob:
    locale: str
    style_compact: str
    core_path: str
    cjk_base_path: str
    output_dir: str
    font_config: ResolvedBuildConfig
    build_option: RuntimeBuildPlan


@dataclass(frozen=True)
class CJKStaticBaseProfile:
    output_locale: str
    base_dir: str
    family_name_compact: str
    font_config: ResolvedBuildConfig


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


def build_mono_job(job: MonoBuildJob) -> None:
    build_mono(job.font_basename, job.font_config, job.build_option)


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


def build_mono_autohint_job(job: MonoAutohintJob) -> None:
    build_mono_autohint(job.font_basename, job.font_config, job.build_option)


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


def build_nf_job(job: NerdFontBuildJob) -> None:
    get_ttfont = (
        build_nf_by_font_patcher
        if job.use_font_patcher
        else build_nf_by_prebuild_nerd_font
    )
    build_nf(job.font_basename, get_ttfont, job.font_config, job.build_option)


def run_process_jobs(pool_size: int, worker: Callable, jobs: list) -> None:
    """Run pickle-safe top-level worker jobs in parallel."""
    if pool_size <= 1:
        for job in jobs:
            worker(job)
        return

    first_exc: Exception | None = None
    with ProcessPoolExecutor(max_workers=pool_size) as executor:
        futures = {executor.submit(worker, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                for submitted in futures:
                    if not submitted.done():
                        submitted.cancel()
                if not first_exc:
                    first_exc = e
                    raise e


def select_build_files(
    directory: str,
    target_styles: list[str] | None = None,
    preserve_nf: bool = False,
) -> list[str]:
    if target_styles is None:
        return listdir(directory)

    files = []
    for file_name in listdir(directory):
        if file_name.split("-")[-1][:-4] in target_styles:
            files.append(file_name)
        elif preserve_nf and "NF" in file_name:
            continue
        else:
            remove(joinPaths(directory, file_name))
    return files


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
            style_compact = (f"{base_name}Italic" if is_italic else base_name).replace(
                "RegularItalic", "Italic"
            )
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
        futures = [
            executor.submit(instantiate_maple_static_font_job, job) for job in jobs
        ]
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


def ensure_cjk_variable_fonts(
    locale: str,
    locale_config,
    preset_spec,
    preset_config,
) -> tuple[Path, Path] | None:
    regular_path = preset_config.output.dir / preset_config.output.regular_variable
    italic_path = preset_config.output.dir / preset_config.output.italic_variable

    if not locale_config.clean_cache and regular_path.exists() and italic_path.exists():
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
        (
            False,
            Path(build_option.output_variable)
            / f"{font_config.family_name_compact}[wght].ttf",
        ),
        (
            True,
            Path(build_option.output_variable)
            / f"{font_config.family_name_compact}-Italic[wght].ttf",
        ),
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
            output_path = output_dir / merged_variable_name(
                postscript_prefix, is_italic
            )
            print(
                f"👉 Merge {preset_spec.family_suffix} variable font: +{len(added_glyphs)} glyphs, +{added_codepoints} unicodes"
            )
            merged_font.save(output_path)
            print(f"✅ Saved merged variable font: {output_path}")
            output_paths.append(output_path)
        finally:
            merged_font.close()

    return output_paths[0], output_paths[1]


def cjk_static_base_profiles(
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
    locale: str,
) -> list[CJKStaticBaseProfile]:
    profiles: list[CJKStaticBaseProfile] = []
    should_build_nf_cjk = (
        build_option.is_nf_built and font_config.cjk.locales[locale].with_nerd_font
    )
    if should_build_nf_cjk:
        nf_suffix = f"NF{font_config.get_nf_suffix()}"
        nf_font_config = deepcopy(font_config)
        nf_font_config.identity.family_name = f"{font_config.family_name} {nf_suffix}"
        nf_font_config.identity.family_name_compact = (
            f"{font_config.family_name_compact}-{nf_suffix}"
        )
        profiles.append(
            CJKStaticBaseProfile(
                output_locale=f"NF-{locale.upper()}",
                base_dir=build_option.output_nf,
                family_name_compact=f"{font_config.family_name_compact}-{nf_suffix}",
                font_config=nf_font_config,
            )
        )

    if not should_build_nf_cjk or font_config.use_cjk_both:
        profiles.append(
            CJKStaticBaseProfile(
                output_locale=locale.upper(),
                base_dir=build_option.ttf_base_dir,
                family_name_compact=font_config.family_name_compact,
                font_config=font_config,
            )
        )

    return profiles


def instantiate_cjk_extended_static_fonts(
    locale: str,
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
    merged_paths: tuple[Path, Path],
    target_styles: list[str] | None,
    output_locale: str | None = None,
) -> Path:
    locale_config = font_config.cjk.locales[locale]
    preset_spec = get_preset(locale)
    output_dir = static_output_dir(build_option.output_dir, output_locale or locale)
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
                print(
                    f"👉 Instantiate {preset_spec.family_suffix} static font: {style_compact}"
                )
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


def merge_cached_cjk_static_font_job(job: CJKStaticMergeJob) -> None:
    preset_spec = get_preset(job.locale)
    print(
        f"👉 Merge cached {preset_spec.family_suffix} static font: {job.style_compact}"
    )
    static_font = merge_ttfonts(
        base_font_path=job.core_path,
        extra_font_path=job.cjk_base_path,
    )
    try:
        postscript_name = postprocess_cjk_extended_static_font(
            static_font,
            job.locale,
            job.font_config,
            job.build_option,
            job.style_compact,
        )
        static_font.save(Path(job.output_dir) / f"{postscript_name}.ttf")
    finally:
        static_font.close()


def cached_cjk_variable_paths(preset_config: CJKBuildConfig) -> tuple[Path, Path]:
    return (
        preset_config.output.dir / preset_config.output.regular_variable,
        preset_config.output.dir / preset_config.output.italic_variable,
    )


def load_cached_cjk_static_fonts(
    cache_dir: Path,
    static_file_prefix: str,
) -> dict[str, Path]:
    cached_fonts: dict[str, Path] = {}
    if not cache_dir.is_dir():
        return cached_fonts
    for font_path in sorted(cache_dir.glob("*.ttf")):
        style_compact = get_static_style_name(font_path, static_file_prefix)
        if not style_compact:
            continue
        cached_fonts[style_compact] = font_path
    return cached_fonts


def build_cjk_extended_static_fonts_from_cache(
    locale: str,
    font_config: ResolvedBuildConfig,
    build_option: RuntimeBuildPlan,
    target_styles: list[str] | None,
) -> bool:
    locale_config = font_config.cjk.locales[locale]
    preset_spec = get_preset(locale)
    preset_config = build_preset_config(locale)
    cache_dir = get_cached_cjk_static_dir(locale)
    static_file_prefix = preset_config.naming.static_file_prefix
    base_profiles = cjk_static_base_profiles(font_config, build_option, locale)
    profile_core_fonts = [
        (
            profile,
            get_core_static_font_styles(
                profile.base_dir,
                profile.family_name_compact,
                target_styles,
            ),
        )
        for profile in base_profiles
    ]
    profile_core_fonts = [
        (profile, core_fonts)
        for profile, core_fonts in profile_core_fonts
        if core_fonts
    ]
    if not profile_core_fonts:
        return False

    cached_fonts = load_cached_cjk_static_fonts(cache_dir, static_file_prefix)
    required_styles = sorted(
        {style for _, core_fonts in profile_core_fonts for style, _ in core_fonts}
    )
    missing_styles = [style for style in required_styles if style not in cached_fonts]

    if locale_config.clean_cache or missing_styles:
        if missing_styles:
            print(
                f"⚠️ Cached {preset_spec.family_suffix} static fonts are incomplete: "
                f"{', '.join(missing_styles)}"
            )
        build_cjk_fonts(preset_config)
        cache_dir = preset_config.output.dir / preset_config.output.static_dir
        cached_fonts = load_cached_cjk_static_fonts(cache_dir, static_file_prefix)
        missing_styles = [
            style for style in required_styles if style not in cached_fonts
        ]

    if missing_styles:
        raise FileNotFoundError(
            f"Cached {preset_spec.family_suffix} static font generation did not "
            f"produce required style(s): {', '.join(missing_styles)}"
        )

    print(f"♻️ Reuse cached {preset_spec.family_suffix} static fonts: {cache_dir}")

    jobs: list[CJKStaticMergeJob] = []
    for profile, core_fonts in profile_core_fonts:
        output_dir = static_output_dir(build_option.output_dir, profile.output_locale)
        output_dir.mkdir(parents=True, exist_ok=True)
        jobs.extend(
            CJKStaticMergeJob(
                locale=locale,
                style_compact=style_compact,
                core_path=str(core_path),
                cjk_base_path=str(cached_fonts[style_compact]),
                output_dir=str(output_dir),
                font_config=profile.font_config,
                build_option=build_option,
            )
            for style_compact, core_path in core_fonts
        )

    run_process_jobs(
        font_config.pool_size,
        merge_cached_cjk_static_font_job,
        jobs,
    )

    if locale_config.use_hinted:
        print(f"Auto hinting all {preset_spec.family_suffix} glyphs")
        for profile, _ in profile_core_fonts:
            run(
                f"ftcli ttf autohint {static_output_dir(build_option.output_dir, profile.output_locale)}"
            )

    return True


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
        if not persist_variable and build_cjk_extended_static_fonts_from_cache(
            locale,
            font_config,
            build_option,
            target_styles,
        ):
            built_any = True
            continue

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
    mono_jobs = [
        MonoBuildJob(
            font_basename=file_name,
            font_config=font_config,
            build_option=build_option,
        )
        for file_name in select_build_files(build_option.output_ttf, target_styles)
    ]
    run_process_jobs(
        font_config.pool_size,
        build_mono_job,
        mono_jobs,
    )

    autohint_jobs = [
        MonoAutohintJob(
            font_basename=file_name,
            font_config=font_config,
            build_option=build_option,
        )
        for file_name in select_build_files(build_option.output_ttf, target_styles)
    ]
    run_process_jobs(
        font_config.pool_size,
        build_mono_autohint_job,
        autohint_jobs,
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

    _version = font_config.nerd_font.version
    print(
        f"\n🔧 Patch Nerd-Font v{_version} using {'Font Patcher' if use_font_patcher else 'prebuild base font'}...\n"
    )

    jobs = [
        NerdFontBuildJob(
            font_basename=file_name,
            use_font_patcher=use_font_patcher,
            font_config=font_config,
            build_option=build_option,
        )
        for file_name in select_build_files(
            build_option.ttf_base_dir,
            target_styles,
            preserve_nf=True,
        )
    ]
    run_process_jobs(
        font_config.pool_size,
        build_nf_job,
        jobs,
    )
    build_option.is_nf_built = True


class MapleBuildPipeline:
    """Coordinate the Maple Mono build pipeline without crossing process boundaries."""

    def __init__(
        self,
        font_config: ResolvedBuildConfig,
        build_option: RuntimeBuildPlan,
    ) -> None:
        self.font_config = font_config
        self.build_option = build_option
        self.should_use_cache = font_config.cache
        self.target_styles = self._resolve_target_styles()
        self.start_time = 0.0

    def build(self) -> None:
        self._prepare_outputs()
        self._start_build()
        self._build_base_outputs()
        self._build_variant_outputs()
        self._write_build_config()
        self._archive_outputs()
        self._finish_build()

    def _resolve_target_styles(self) -> list[str] | None:
        if self.font_config.least_styles:
            return ["Regular", "Bold", "Italic", "BoldItalic"]
        if self.font_config.debug:
            return ["Regular", "Italic"]
        return None

    def _prepare_outputs(self) -> None:
        if not self.should_use_cache:
            print("🧹 Clean cache...\n")
            shutil.rmtree(self.build_option.output_dir, ignore_errors=True)
            shutil.rmtree(self.build_option.output_woff2, ignore_errors=True)
        ensure_base_output_dirs(self.build_option)

    def _start_build(self) -> None:
        self.start_time = time.time()
        print(
            f"🚩 Start building {self.font_config.family_name} {self.font_config.version_str} ...\n"
        )

    def _build_base_outputs(self) -> None:
        if self.should_use_cache and self.build_option.has_cache:
            return
        build_variable_fonts(self.font_config, self.build_option)
        build_base_fonts(self.font_config, self.build_option, self.target_styles)

    def _build_variant_outputs(self) -> None:
        build_nerd_fonts(self.font_config, self.build_option, self.target_styles)
        build_cjk_extended_outputs(
            self.font_config,
            self.build_option,
            self.target_styles,
        )
        cleanup_unselected_base_formats(self.font_config, self.build_option)

    def _write_build_config(self) -> None:
        with open(
            joinPaths(self.build_option.output_dir, "build-config.json"),
            "w",
            encoding="utf-8",
        ) as config_file:
            config_file.write(
                json.dumps(
                    self.font_config.to_build_record(),
                    indent=4,
                )
            )

    def _archive_outputs(self) -> None:
        if not self.font_config.archive:
            return

        print("\n🚀 archive files...\n")
        archive_dir_name = "archive"
        archive_dir = joinPaths(self.build_option.output_dir, archive_dir_name)
        makedirs(archive_dir, exist_ok=True)

        for file_name in listdir(self.build_option.output_dir):
            if file_name == archive_dir_name or file_name.endswith(".json"):
                continue

            suffix = ""
            cjk_archive_dirs = {
                locale.upper() for locale in self.font_config.get_selected_cjk_locales()
            }
            nf_cjk_archive_dirs = {
                f"NF-{locale.upper()}"
                for locale in self.font_config.get_selected_cjk_locales()
            }
            if file_name in {"NF", *cjk_archive_dirs, *nf_cjk_archive_dirs}:
                if not self.font_config.use_hinted:
                    suffix = "-unhinted"
            elif self.should_use_cache:
                continue

            sha256, zip_file_name_without_ext = archive_fonts(
                family_name_compact=self.font_config.family_name_compact,
                suffix=suffix,
                source_file_or_dir_path=joinPaths(
                    self.build_option.output_dir,
                    file_name,
                ),
                build_config_path=joinPaths(
                    self.build_option.output_dir,
                    "build-config.json",
                ),
                target_parent_dir_path=archive_dir,
            )
            with open(
                joinPaths(archive_dir, f"{zip_file_name_without_ext}.sha256"),
                "w",
                encoding="utf-8",
            ) as hash_file:
                hash_file.write(sha256)

            print(f"👉 archive: {file_name}")

    def _finish_build(self) -> None:
        if is_ci():
            return

        freeze_str = (
            self.font_config.freeze_config_str
            if self.font_config.freeze_config_str != ""
            else "default config"
        )
        end_time = time.time()
        date_time_fmt = time.strftime("%H:%M:%S", time.localtime(end_time))
        time_diff = end_time - self.start_time
        output = joinPaths(getcwd().replace("\\", "/"), self.build_option.output_dir)
        print(
            f"\n🏁 Build finished at {date_time_fmt}, cost {time_diff:.2f} s, family name is {self.font_config.family_name}, {freeze_str}\n   See your fonts in {output}"
        )


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

    MapleBuildPipeline(font_config, build_option).build()


if __name__ == "__main__":
    from source.py.build.cli import main as cli_main

    cli_main()

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
from typing import Callable, cast
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from ttfautohint import StemWidthMode, ttfautohint
from scripts.font_ops.glyph_transform import smart_change_width
from scripts.config.base import ResolvedBuildConfig, ResolvedCJKBuildEntry
from scripts.utils.errors import BuildDependencyError
from scripts.config.paths import (
    merged_variable_name,
    static_output_dir,
    variable_output_dir,
)
from scripts.config.resolver import BuildConfigResolver, BuildRuntimeContext
from scripts.cjk.static import (
    apply_cjk_meta_table,
    build_cjk_family_name,
    build_cjk_postscript_prefix,
    get_core_static_font_styles,
    get_static_style_name,
    postprocess_cjk_extended_static_font,
)
from scripts.cjk.pipeline import (
    build_cjk_fonts,
    create_font_executor,
    feature_weight_instances,
    get_static_worker_font,
)
from scripts.cjk.variable import load_font_eager, merge_vf
from scripts.utils.dependencies import check_ftcli
from scripts.utils.files import archive_fonts, join_path
from scripts.utils.process import is_ci, run as run_command
from scripts.feature.apply import patch_font_feature
from scripts.font_ops.glyphs import (
    GlyphsSourceReport,
    SourceCompatibilityError,
    SourceStyle,
    generate_variable_font,
    validate_source_reports,
)
from scripts.font_ops.fonttools_types import HeadTable, OS2Table
from scripts.font_ops.merge import merge_ttfonts
from scripts.font_ops.metrics import adjust_line_height, verify_glyph_width
from scripts.font_ops.names import (
    get_unique_identifier,
    parse_style_name,
    update_font_names,
)
from scripts.font_ops.opentype import (
    add_gasp,
    add_ital_axis_to_stat,
    alias_codepoints,
    patch_instance,
)


FONT_VERSION = "v7.9"
# =========================================================================================


@dataclass(frozen=True)
class MonoBuildJob:
    font_basename: str
    font_config: ResolvedBuildConfig
    runtime_context: BuildRuntimeContext


@dataclass(frozen=True)
class MonoAutohintJob:
    font_basename: str
    font_config: ResolvedBuildConfig
    runtime_context: BuildRuntimeContext


@dataclass(frozen=True)
class NerdFontBuildJob:
    font_basename: str
    use_font_patcher: bool
    font_config: ResolvedBuildConfig
    runtime_context: BuildRuntimeContext


@dataclass(frozen=True)
class CJKStaticMergeJob:
    entry: ResolvedCJKBuildEntry
    style_compact: str
    core_path: str
    cjk_base_path: str
    output_dir: str
    font_config: ResolvedBuildConfig
    runtime_context: BuildRuntimeContext


@dataclass(frozen=True)
class CJKStaticBaseProfile:
    output_locale: str
    base_dir: str
    family_name_compact: str
    font_config: ResolvedBuildConfig


def build_mono(
    f: str, font_config: ResolvedBuildConfig, runtime_context: BuildRuntimeContext
):
    print(f"👉 Minimal version for {f}")
    source_path = join_path(runtime_context.output_ttf, f)

    run_command(f"ftcli fix italic-angle {source_path}")
    run_command(f"ftcli fix monospace {source_path}")
    run_command(f"ftcli name strip-names {source_path}")
    run_command(f"ftcli font correct-contours {source_path}")
    run_command(f"ftcli ttf dehint {source_path}")
    run_command(f"ftcli fix transformed-components {source_path}")

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
        cast(OS2Table, font["OS/2"]).usWeightClass = 250
    elif style_with_prefix_space == " ExtraLight":
        cast(OS2Table, font["OS/2"]).usWeightClass = 275

    patch_font_feature(
        config=font_config,
        font=font,
        issue_fea_dir=runtime_context.output_dir,
        is_italic=is_italic,
        is_cn=False,
        is_variable=False,
        is_hinted=False,
        fea_path=runtime_context.feature_file_path(is_italic),
    )

    verify_glyph_width(
        font=font,
        expect_widths=font_config.get_valid_glyph_width_list(),
        file_name=postscript_name,
    )

    remove(source_path)
    target_path = join_path(runtime_context.output_ttf, f"{postscript_name}.ttf")
    font.save(target_path)

    if font_config.wants_format("woff2") and not font_config.debug:
        print(f"Convert {postscript_name}.ttf to WOFF2")
        run_command(
            f"ftcli converter ft2wf {target_path} -out {runtime_context.output_woff2} -f woff2"
        )

    if font_config.wants_format("otf") and not font_config.debug:
        _otf_path = join_path(
            runtime_context.output_otf,
            path.basename(target_path).replace(".ttf", ".otf"),
        )
        print(f"Convert {postscript_name}.ttf to OTF")
        run_command(
            f"ftcli converter ttf2otf {target_path} -out {runtime_context.output_otf}"
        )
        print(f"Optimize {postscript_name}.otf")
        run_command(f"ftcli font correct-contours {_otf_path}")
        run_command(f"ftcli cff set-names --version {font_config.version} {_otf_path}")


def build_mono_job(job: MonoBuildJob) -> None:
    build_mono(job.font_basename, job.font_config, job.runtime_context)


def build_mono_autohint(
    f: str, font_config: ResolvedBuildConfig, runtime_context: BuildRuntimeContext
):
    style_compact = f.split("-")[-1].split(".")[0]
    postscript_name = f"{font_config.family_name_compact}-{style_compact}"
    print(f"👉 Auto hint {postscript_name}.ttf")

    source_path = join_path(runtime_context.output_ttf, f)
    font = TTFont(source_path)
    is_italic = "Italic" in style_compact
    patch_font_feature(
        config=font_config,
        font=font,
        issue_fea_dir=runtime_context.output_dir,
        is_italic=is_italic,
        is_cn=False,
        is_variable=False,
        is_hinted=True,
        fea_path=runtime_context.feature_file_path(is_italic),
    )

    # Ensure flags to respect hint info
    head = cast(HeadTable, font["head"])
    head.flags |= 1 << 2 | 1 << 3

    param: dict | None = font_config.ttfautohint_param

    buf = BytesIO()
    font.save(buf)
    font.close()

    # https://freetype.org/ttfautohint/doc/ttfautohint.html#options
    # Also see `ttfautohint.options.USER_OPTIONS`
    options = {
        "in_buffer": buf.getvalue(),
        "reference_file": join_path(
            runtime_context.output_ttf, f"{font_config.family_name_compact}-Regular.ttf"
        ),
        "out_file": join_path(
            runtime_context.output_ttf_hinted, f"{postscript_name}.ttf"
        ),
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
    build_mono_autohint(job.font_basename, job.font_config, job.runtime_context)


def build_nf_by_prebuild_nerd_font(
    font_basename: str,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
) -> TTFont:
    suffix = font_config.get_nf_suffix()
    if suffix:
        suffix = "-" + suffix

    nf_base_font_path = f"{runtime_context.src_dir}/MapleMono-NF-Base{suffix}.ttf"
    tmp_target_path = None
    if font_config.get_width_name():
        tmp_font = TTFont(nf_base_font_path)
        smart_change_width(
            font=tmp_font,
            target_width=font_config.get_target_width(),
            original_ref_width=font_config.glyph_width,
            also_scale_y=True,
        )
        tmp_target_path = f"{runtime_context.output_dir}/NF-Base-{font_basename}"
        tmp_font.save(tmp_target_path)

    result = merge_ttfonts(
        base_font_path=join_path(runtime_context.ttf_base_dir, font_basename),
        extra_font_path=tmp_target_path or nf_base_font_path,
    )

    if tmp_target_path is not None:
        remove(tmp_target_path)

    return result


def build_nf_by_font_patcher(
    font_basename: str,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
) -> TTFont:
    """
    full args: https://github.com/ryanoasis/nerd-fonts?tab=readme-ov-file#font-patcher
    """
    if runtime_context.font_forge_bin is None:
        raise BuildDependencyError(
            "FontForge bin is unavailable after dependency validation"
        )
    _nf_args = [
        runtime_context.font_forge_bin,
        "FontPatcher/font-patcher",
        "-l",
        "--careful",
        "--outputdir",
        runtime_context.output_nf,
    ] + font_config.nerd_font.glyphs

    if font_config.nerd_font.propo:
        _nf_args += ["--variable-width-glyphs"]
    elif font_config.nerd_font.mono:
        _nf_args += ["--mono"]

    extra_args = font_config.nerd_font.extra_args
    _nf_args += extra_args

    run_command(_nf_args + [join_path(runtime_context.ttf_base_dir, font_basename)])

    nf_file_name = "NerdFont" + font_config.get_nf_suffix()

    _path = join_path(
        runtime_context.output_nf, font_basename.replace("-", f"{nf_file_name}-")
    )
    font = TTFont(_path)
    remove(_path)

    # Check if the glyph 'nonmarkingreturn' exists in the font
    extra_name = "nonmarkingreturn"
    if extra_name in font.getGlyphNames():
        font["hmtx"][extra_name] = (600, 0)
    return font


def build_nf(
    f: str,
    get_ttfont: Callable[[str, ResolvedBuildConfig, BuildRuntimeContext], TTFont],
    use_font_patcher: bool,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
):
    print(f"👉 NerdFont{font_config.get_nf_suffix()} version for {f}")
    nf_font = get_ttfont(f, font_config, runtime_context)

    # format font name
    style_compact_nf = f.split("-")[-1].split(".")[0]

    style_nf_with_prefix_space, style_in_2, style_in_17, is_skip_sufamily, _ = (
        parse_style_name(
            style_name_compact=style_compact_nf,
        )
    )

    nf_sym = f"NF{font_config.get_nf_suffix_compact()}"
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
            nf_font, font_config.line_height, runtime_context.resolved_vertical_metric
        )

    if not (use_font_patcher or font_config.get_nf_suffix() == "Propo"):
        verify_glyph_width(
            font=nf_font,
            expect_widths=font_config.get_valid_glyph_width_list(),
            file_name=postscript_name,
        )

    target_path = join_path(
        runtime_context.output_nf,
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
    build_nf(
        job.font_basename,
        get_ttfont,
        job.use_font_patcher,
        job.font_config,
        job.runtime_context,
    )


def run_process_jobs(pool_size: int, worker: Callable, jobs: list) -> None:
    """Run pickle-safe top-level worker jobs in parallel."""
    if pool_size <= 1:
        for job in jobs:
            worker(job)
        return

    with ProcessPoolExecutor(max_workers=pool_size) as executor:
        futures = [executor.submit(worker, job) for job in jobs]
        try:
            for future in as_completed(futures):
                future.result()
        except Exception:
            for future in futures:
                if not future.done():
                    future.cancel()
            raise


def is_target_style_file(file_name: str, target_styles: list[str] | None) -> bool:
    if target_styles is None:
        return True
    return file_name.split("-")[-1][:-4] in target_styles


def collect_build_files(
    directory: str,
    target_styles: list[str] | None = None,
) -> list[str]:
    return [
        file_name
        for file_name in sorted(listdir(directory))
        if is_target_style_file(file_name, target_styles)
    ]


def prune_build_files(
    directory: str,
    target_styles: list[str] | None = None,
    preserve_nf: bool = False,
) -> None:
    if target_styles is None:
        return

    for file_name in listdir(directory):
        if is_target_style_file(file_name, target_styles):
            continue
        if preserve_nf and "NF" in file_name:
            continue
        remove(join_path(directory, file_name))


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
    runtime_context: BuildRuntimeContext,
) -> None:
    print("Instantiate TTF")
    jobs: list[MapleStaticInstanceJob] = []
    regular_input_path = join_path(
        runtime_context.output_variable,
        f"{font_config.family_name_compact}[wght].ttf",
    )
    regular_var_font = load_font_eager(regular_input_path)
    try:
        instances = feature_weight_instances(regular_var_font)
    finally:
        regular_var_font.close()

    for is_italic in (False, True):
        input_path = join_path(
            runtime_context.output_variable,
            f"{font_config.family_name_compact}{'-Italic' if is_italic else ''}[wght].ttf",
        )
        for instance in instances:
            base_name = instance.name.replace(" Italic", "").replace(" ", "")
            style_compact = (f"{base_name}Italic" if is_italic else base_name).replace(
                "RegularItalic", "Italic"
            )
            output_path = join_path(
                runtime_context.output_ttf,
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
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
):
    """Generate variable fonts from Glyphs sources and apply project metadata."""
    source_dir = Path(runtime_context.src_dir)
    temp_path = Path(runtime_context.output_dir) / "temp"
    source_specs: tuple[tuple[Path, SourceStyle, Path], ...] = (
        (
            source_dir / "MapleMono[wght].glyphs",
            "regular",
            temp_path / "regular-raw.ttf",
        ),
        (
            source_dir / "MapleMono-Italic[wght].glyphs",
            "italic",
            temp_path / "italic-raw.ttf",
        ),
    )

    output_dir = Path(runtime_context.output_variable)
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(temp_path, ignore_errors=True)
    temp_path.mkdir(parents=True)
    try:
        reports: list[GlyphsSourceReport] = []
        with ProcessPoolExecutor(max_workers=len(source_specs)) as executor:
            futures = [
                executor.submit(
                    generate_variable_font,
                    source_path,
                    style,
                    raw_path,
                )
                for source_path, style, raw_path in source_specs
            ]
            for future in as_completed(futures):
                reports.append(future.result())
        validate_source_reports(reports, runtime_context.output_dir)

        processed_paths: dict[str, Path] = {}
        for source_path, style, raw_path in source_specs:
            print(f"👉 Postprocess variable font from {source_path.name}")
            is_italic = style == "italic"
            file_name = font_config.family_name_compact
            if is_italic:
                file_name += "-Italic"
            output_name = f"{file_name}[wght].ttf"
            font = TTFont(raw_path)
            try:
                alias_codepoints(font=font)

                if font_config.get_width_name():
                    smart_change_width(
                        font=font,
                        target_width=font_config.get_target_width(),
                        original_ref_width=font_config.glyph_width,
                    )

                patch_font_feature(
                    config=font_config,
                    font=font,
                    issue_fea_dir=runtime_context.output_dir,
                    is_italic=is_italic,
                    is_cn=False,
                    is_variable=True,
                    is_hinted=False,
                    fea_path=runtime_context.feature_file_path(is_italic),
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
                    calculated_metric = (
                        font["hhea"].ascender,
                        font["hhea"].descender,
                    )
                    runtime_context.resolved_vertical_metric = calculated_metric
                    adjust_line_height(
                        font,
                        font_config.line_height,
                        calculated_metric,
                    )

                verify_glyph_width(
                    font=font,
                    expect_widths=font_config.get_valid_glyph_width_list(),
                    file_name=output_name,
                )
                add_gasp(font)

                processed_path = temp_path / output_name
                font.save(processed_path)
                processed_paths[style] = processed_path
            finally:
                font.close()

        for processed_path in processed_paths.values():
            shutil.copy2(processed_path, output_dir / processed_path.name)
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)

    print("\n✨ Instantiate and optimize fonts...\n")

    print("Check and optimize variable fonts")

    # Italic angle is correct here.
    # run(f"ftcli fix italic-angle {runtime_context.output_variable}")

    run_command(f"ftcli fix monospace {runtime_context.output_variable}")
    # run(f"ftcli fix vertical-metrics {runtime_context.output_variable}")
    # run(f"ftcli name del-mac-names -r {runtime_context.output_variable}")

    instantiate_base_static_fonts(font_config, runtime_context)


def ensure_cjk_variable_fonts(
    entry: ResolvedCJKBuildEntry,
) -> tuple[Path, Path] | None:
    preset_config = entry.build_config
    regular_path = preset_config.output.dir / preset_config.output.regular_variable
    italic_path = preset_config.output.dir / preset_config.output.italic_variable

    if (
        not entry.common_options.clean_cache
        and regular_path.exists()
        and italic_path.exists()
    ):
        print(
            f"♻️ Reuse cached {entry.display_name} variable fonts: "
            f"{regular_path.name}, {italic_path.name}"
        )
        return regular_path, italic_path

    try:
        build_cjk_fonts(preset_config, vf_only=True)
    except FileNotFoundError as error:
        print(f"⚠️ Skip {entry.display_name} extended fonts: {error}")
        return None

    if not regular_path.exists() or not italic_path.exists():
        print(
            f"⚠️ Skip {entry.display_name} extended fonts: "
            "variable font outputs were not generated"
        )
        return None
    return regular_path, italic_path


def build_cjk_extended_variable_fonts(
    entry: ResolvedCJKBuildEntry,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    output_dir: Path,
) -> tuple[Path, Path] | None:
    base_variable_paths = ensure_cjk_variable_fonts(entry)
    if base_variable_paths is None:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    core_pairs = (
        (
            False,
            Path(runtime_context.output_variable)
            / f"{font_config.family_name_compact}[wght].ttf",
        ),
        (
            True,
            Path(runtime_context.output_variable)
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
            locale_suffix = entry.locale_name
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
                    narrow=entry.common_options.narrow,
                    variable=True,
                ),
                is_skip_subfamily=True,
            )
            if (
                entry.is_builtin
                and entry.common_options.fix_meta_table
                and entry.preset_spec
            ):
                apply_cjk_meta_table(
                    merged_font,
                    entry.preset_spec.meta_languages,
                    entry.preset_spec.code_page_range1,
                )
            output_path = output_dir / merged_variable_name(
                postscript_prefix, is_italic
            )
            print(
                f"👉 Merge {entry.display_name} variable font: +{len(added_glyphs)} glyphs, +{added_codepoints} unicodes"
            )
            merged_font.save(output_path)
            print(f"✅ Saved merged variable font: {output_path}")
            output_paths.append(output_path)
        finally:
            merged_font.close()

    return output_paths[0], output_paths[1]


def cjk_static_base_profiles(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    entry: ResolvedCJKBuildEntry,
) -> list[CJKStaticBaseProfile]:
    profiles: list[CJKStaticBaseProfile] = []
    should_build_nf_cjk = (
        runtime_context.is_nf_built and entry.common_options.with_nerd_font
    )
    if should_build_nf_cjk:
        nf_suffix = f"NF{font_config.get_nf_suffix_compact()}"
        nf_font_config = deepcopy(font_config)
        nf_font_config.identity.family_name = f"{font_config.family_name} {nf_suffix}"
        nf_font_config.identity.family_name_compact = (
            f"{font_config.family_name_compact}-{nf_suffix}"
        )
        profiles.append(
            CJKStaticBaseProfile(
                output_locale=f"NF-{entry.locale_name}",
                base_dir=runtime_context.output_nf,
                family_name_compact=f"{font_config.family_name_compact}-{nf_suffix}",
                font_config=nf_font_config,
            )
        )

    if not should_build_nf_cjk or font_config.use_cjk_both:
        profiles.append(
            CJKStaticBaseProfile(
                output_locale=entry.locale_name,
                base_dir=runtime_context.ttf_base_dir,
                family_name_compact=font_config.family_name_compact,
                font_config=font_config,
            )
        )

    return profiles


def instantiate_cjk_extended_static_fonts(
    entry: ResolvedCJKBuildEntry,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    merged_paths: tuple[Path, Path],
    target_styles: list[str] | None,
    output_locale: str | None = None,
) -> Path:
    output_dir = static_output_dir(
        runtime_context.output_dir,
        output_locale or entry.locale_name,
    )
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
                    f"👉 Instantiate {entry.display_name} static font: {style_compact}"
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
                        entry,
                        font_config,
                        runtime_context,
                        style_compact,
                        entry.locale_name,
                    )
                    static_font.save(output_dir / f"{postscript_name}.ttf")
                finally:
                    static_font.close()
        finally:
            var_font.close()

    if entry.common_options.use_hinted:
        print(f"Auto hinting all {entry.display_name} glyphs")
        run_command(f"ftcli ttf autohint {output_dir}")

    return output_dir


def merge_cached_cjk_static_font_job(job: CJKStaticMergeJob) -> None:
    print(f"👉 Merge cached {job.entry.display_name} static font: {job.style_compact}")
    static_font = merge_ttfonts(
        base_font_path=job.core_path,
        extra_font_path=job.cjk_base_path,
    )
    try:
        postscript_name = postprocess_cjk_extended_static_font(
            static_font,
            job.entry,
            job.font_config,
            job.runtime_context,
            job.style_compact,
            job.entry.locale_name,
        )
        static_font.save(Path(job.output_dir) / f"{postscript_name}.ttf")
    finally:
        static_font.close()


def cached_cjk_variable_paths(entry: ResolvedCJKBuildEntry) -> tuple[Path, Path]:
    preset_config = entry.build_config
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
    entry: ResolvedCJKBuildEntry,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
) -> bool:
    base_profiles = cjk_static_base_profiles(
        font_config,
        runtime_context,
        entry,
    )
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

    required_styles = sorted(
        {style for _, core_fonts in profile_core_fonts for style, _ in core_fonts}
    )
    resolved_base = runtime_context.resolve_cjk_static_base(
        entry,
        required_styles,
    )
    cached_fonts = load_cached_cjk_static_fonts(
        resolved_base.static_dir,
        resolved_base.static_file_prefix,
    )
    missing_styles = [style for style in required_styles if style not in cached_fonts]

    if missing_styles:
        raise FileNotFoundError(
            f"Resolved {entry.locale_name} static CJK base from "
            f"{resolved_base.source_kind}, but style(s) are missing: "
            f"{', '.join(missing_styles)}"
        )

    print(
        f"♻️ Use {entry.display_name} static fonts from "
        f"{resolved_base.source_kind}: {resolved_base.static_dir}"
    )

    jobs: list[CJKStaticMergeJob] = []
    for profile, core_fonts in profile_core_fonts:
        output_dir = static_output_dir(
            runtime_context.output_dir, profile.output_locale
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        jobs.extend(
            CJKStaticMergeJob(
                entry=entry,
                style_compact=style_compact,
                core_path=str(core_path),
                cjk_base_path=str(cached_fonts[style_compact]),
                output_dir=str(output_dir),
                font_config=profile.font_config,
                runtime_context=runtime_context,
            )
            for style_compact, core_path in core_fonts
        )

    run_process_jobs(
        font_config.pool_size,
        merge_cached_cjk_static_font_job,
        jobs,
    )

    if entry.common_options.use_hinted:
        print(f"Auto hinting all {entry.display_name} glyphs")
        for profile, _ in profile_core_fonts:
            run_command(
                f"ftcli ttf autohint {static_output_dir(runtime_context.output_dir, profile.output_locale)}"
            )

    return True


def build_cjk_extended_outputs(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
) -> None:
    if font_config.cjk_output_format == "variable":
        build_cjk_extended_variable_outputs(font_config, runtime_context)
    else:
        build_cjk_extended_static_outputs(font_config, runtime_context, target_styles)


def build_cjk_extended_variable_outputs(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
) -> None:
    entries = font_config.get_selected_cjk_entries()
    if not entries:
        return

    built_any = False
    for entry in entries:
        merged_paths = build_cjk_extended_variable_fonts(
            entry,
            font_config,
            runtime_context,
            variable_output_dir(runtime_context.output_dir, entry.locale_name),
        )
        if merged_paths is not None:
            built_any = True

    runtime_context.is_cjk_built = built_any


def build_cjk_extended_static_outputs(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
) -> None:
    entries = font_config.get_selected_cjk_entries()
    if not entries:
        return

    temp_root = Path(runtime_context.output_dir) / ".cjk-temp"
    built_any = False
    for entry in entries:
        if build_cjk_extended_static_fonts_from_cache(
            entry,
            font_config,
            runtime_context,
            target_styles,
        ):
            built_any = True
            continue

        locale_output_dir = temp_root / entry.locale_name.upper()
        merged_paths = build_cjk_extended_variable_fonts(
            entry,
            font_config,
            runtime_context,
            locale_output_dir,
        )
        if merged_paths is None:
            continue
        built_any = True
        instantiate_cjk_extended_static_fonts(
            entry,
            font_config,
            runtime_context,
            merged_paths,
            target_styles,
            entry.locale_name,
        )
        shutil.rmtree(locale_output_dir, ignore_errors=True)

    shutil.rmtree(temp_root, ignore_errors=True)
    runtime_context.is_cjk_built = built_any


def cleanup_unselected_base_formats(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
) -> None:
    if font_config.wants_format("ttf"):
        return

    shutil.rmtree(runtime_context.output_ttf, ignore_errors=True)
    shutil.rmtree(runtime_context.output_ttf_hinted, ignore_errors=True)


def ensure_base_output_dirs(runtime_context: BuildRuntimeContext) -> None:
    makedirs(runtime_context.output_dir, exist_ok=True)
    makedirs(runtime_context.output_variable, exist_ok=True)
    makedirs(runtime_context.output_ttf, exist_ok=True)
    makedirs(runtime_context.output_ttf_hinted, exist_ok=True)


def read_font_vertical_metric(font_path: str | Path) -> tuple[int, int]:
    font = TTFont(font_path)
    try:
        return (font["hhea"].ascender, font["hhea"].descender)
    finally:
        font.close()


def build_base_fonts(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
):
    """Apply mono building and auto-hinting to static TTF fonts."""
    prune_build_files(runtime_context.output_ttf, target_styles)
    mono_jobs = [
        MonoBuildJob(
            font_basename=file_name,
            font_config=font_config,
            runtime_context=runtime_context,
        )
        for file_name in collect_build_files(runtime_context.output_ttf, target_styles)
    ]
    run_process_jobs(
        font_config.pool_size,
        build_mono_job,
        mono_jobs,
    )

    prune_build_files(runtime_context.output_ttf, target_styles)
    autohint_jobs = [
        MonoAutohintJob(
            font_basename=file_name,
            font_config=font_config,
            runtime_context=runtime_context,
        )
        for file_name in collect_build_files(runtime_context.output_ttf, target_styles)
    ]
    run_process_jobs(
        font_config.pool_size,
        build_mono_autohint_job,
        autohint_jobs,
    )


def build_nerd_fonts(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
):
    """Build Nerd Font variants."""
    if not font_config.nerd_font.enable:
        return

    makedirs(runtime_context.output_nf, exist_ok=True)
    use_font_patcher = runtime_context.should_use_font_patcher(font_config)
    runtime_context.ensure_font_patcher_available(font_config)

    _version = font_config.nerd_font.version
    print(
        f"\n🔧 Patch Nerd-Font v{_version} using {'Font Patcher' if use_font_patcher else 'prebuild base font'}...\n"
    )

    prune_build_files(runtime_context.ttf_base_dir, target_styles, preserve_nf=True)
    jobs = [
        NerdFontBuildJob(
            font_basename=file_name,
            use_font_patcher=use_font_patcher,
            font_config=font_config,
            runtime_context=runtime_context,
        )
        for file_name in collect_build_files(
            runtime_context.ttf_base_dir,
            target_styles,
        )
    ]
    run_process_jobs(
        font_config.pool_size,
        build_nf_job,
        jobs,
    )
    runtime_context.is_nf_built = True


class MapleBuildPipeline:
    """Coordinate the Maple Mono build pipeline without crossing process boundaries."""

    def __init__(
        self,
        font_config: ResolvedBuildConfig,
        runtime_context: BuildRuntimeContext,
    ) -> None:
        self.font_config = font_config
        self.runtime_context = runtime_context
        self.should_use_cache = font_config.cache
        self.target_styles = self._resolve_target_styles()
        self.start_time = 0.0

    def build(self) -> None:
        self.prepare_output_root()
        self.start_build_timer()

        if self.should_build_base_outputs():
            build_variable_fonts(self.font_config, self.runtime_context)
            build_base_fonts(self.font_config, self.runtime_context, self.target_styles)
        else:
            self.reuse_base_output_cache()

        if self.should_build_nerd_fonts():
            build_nerd_fonts(self.font_config, self.runtime_context, self.target_styles)
        else:
            print("Skip Nerd Font outputs")

        if self.should_build_cjk_outputs():
            if self.should_persist_cjk_variable_outputs():
                build_cjk_extended_variable_outputs(
                    self.font_config,
                    self.runtime_context,
                )
            else:
                build_cjk_extended_static_outputs(
                    self.font_config,
                    self.runtime_context,
                    self.target_styles,
                )
        else:
            print("Skip CJK outputs")

        if self.should_cleanup_base_static_formats():
            cleanup_unselected_base_formats(self.font_config, self.runtime_context)

        self.write_build_record()

        if self.should_archive_outputs():
            self.archive_outputs()

        self.finish_build()

    def _resolve_target_styles(self) -> list[str] | None:
        if self.font_config.least_styles:
            return ["Regular", "Bold", "Italic", "BoldItalic"]
        if self.font_config.debug:
            return ["Regular", "Italic"]
        return None

    def prepare_output_root(self) -> None:
        if not self.should_use_cache:
            print("🧹 Clean cache...\n")
            shutil.rmtree(self.runtime_context.output_dir, ignore_errors=True)
            shutil.rmtree(self.runtime_context.output_woff2, ignore_errors=True)
        ensure_base_output_dirs(self.runtime_context)

    def start_build_timer(self) -> None:
        self.start_time = time.time()
        print(
            f"🚩 Start building {self.font_config.family_name} {self.font_config.version_str} ...\n"
        )

    def should_build_base_outputs(self) -> bool:
        return not self.should_use_cache or not self.runtime_context.has_cache

    def reuse_base_output_cache(self) -> None:
        regular_variable_path = Path(self.runtime_context.output_variable) / (
            f"{self.font_config.family_name_compact}[wght].ttf"
        )
        if not regular_variable_path.exists():
            raise FileNotFoundError(
                f"Cached variable font not found: {regular_variable_path}"
            )
        self.runtime_context.resolved_vertical_metric = read_font_vertical_metric(
            regular_variable_path
        )
        print("♻️ Reuse cached Variable, TTF, and TTF-AutoHint outputs")

    def should_build_nerd_fonts(self) -> bool:
        return self.font_config.nerd_font.enable

    def should_build_cjk_outputs(self) -> bool:
        return bool(self.font_config.get_selected_cjk_entries())

    def should_persist_cjk_variable_outputs(self) -> bool:
        return self.font_config.cjk_output_format == "variable"

    def should_cleanup_base_static_formats(self) -> bool:
        return not self.font_config.wants_format("ttf")

    def write_build_record(self) -> None:
        with open(
            join_path(self.runtime_context.output_dir, "build-config.json"),
            "w",
            encoding="utf-8",
        ) as config_file:
            config_file.write(
                json.dumps(
                    self.font_config.to_build_record(),
                    indent=4,
                )
            )

    def should_archive_outputs(self) -> bool:
        return self.font_config.archive

    def archive_outputs(self) -> None:
        print("\n🚀 archive files...\n")
        archive_dir_name = "archive"
        archive_dir = join_path(self.runtime_context.output_dir, archive_dir_name)
        makedirs(archive_dir, exist_ok=True)

        for file_name in listdir(self.runtime_context.output_dir):
            if file_name == archive_dir_name or file_name.endswith(".json"):
                continue

            suffix = ""
            cjk_locale_names = {
                entry.locale_name
                for entry in self.font_config.get_selected_cjk_entries()
            }
            cjk_archive_dirs = {locale_name.upper() for locale_name in cjk_locale_names}
            nf_cjk_archive_dirs = {
                f"NF-{locale_name}".upper() for locale_name in cjk_locale_names
            }
            if file_name in {"NF", *cjk_archive_dirs, *nf_cjk_archive_dirs}:
                if not self.font_config.use_hinted:
                    suffix = "-unhinted"
            elif self.should_use_cache:
                continue

            sha256, zip_file_name_without_ext = archive_fonts(
                family_name_compact=self.font_config.family_name_compact,
                suffix=suffix,
                source_file_or_dir_path=join_path(
                    self.runtime_context.output_dir,
                    file_name,
                ),
                build_config_path=join_path(
                    self.runtime_context.output_dir,
                    "build-config.json",
                ),
                target_parent_dir_path=archive_dir,
            )
            with open(
                join_path(archive_dir, f"{zip_file_name_without_ext}.sha256"),
                "w",
                encoding="utf-8",
            ) as hash_file:
                hash_file.write(sha256)

            print(f"👉 archive: {file_name}")

    def finish_build(self) -> None:
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
        output = join_path(getcwd().replace("\\", "/"), self.runtime_context.output_dir)
        print(
            f"\n🏁 Build finished at {date_time_fmt}, cost {time_diff:.2f} s, family name is {self.font_config.family_name}, {freeze_str}\n   See your fonts in {output}"
        )


def run(parsed_args, version: str | None = None):
    global FONT_VERSION
    try:
        check_ftcli()

        version_tag = version or FONT_VERSION
        if version:
            FONT_VERSION = version

        resolver = BuildConfigResolver(version_tag=version_tag)
        font_config = resolver.resolve(parsed_args)
        runtime_context = BuildRuntimeContext.from_config(font_config)

        if parsed_args.dry:
            if is_ci():
                print(json.dumps(font_config.to_dict(), indent=4))
            else:
                print("resolved_config:", json.dumps(font_config.to_dict(), indent=4))
                print(
                    "runtime_context:",
                    json.dumps(runtime_context.to_dict(font_config), indent=4),
                )
            return

        MapleBuildPipeline(font_config, runtime_context).build()
    except (BuildDependencyError, SourceCompatibilityError) as error:
        print(f"❗ {error}")
        raise SystemExit(1) from error


def main(args: list[str] | None = None, version: str | None = None) -> None:
    from scripts.config.cli import parse_args

    run(parse_args(args, version=version), version=version)

#!/usr/bin/env python3
from concurrent.futures import Executor
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import time
from os import environ, listdir, makedirs, remove
from typing import Callable, Literal
from scripts.font_ops.fonttools import TTFont, instantiate_variable_font
from ttfautohint import ttfautohint
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
    autohint_static_fonts,
    build_cjk_fonts,
    feature_weight_instances,
    get_ttfautohint_options,
)
from scripts.cjk.variable import load_font_eager, merge_vf
from scripts.font_ops.conversion import convert_to_web
from scripts.utils.files import archive_fonts, join_path
from scripts.utils.logging import (
    ENVIRONMENT_VARIABLE,
    configure_logging,
    log_task,
    logger,
    set_log_task,
)
from scripts.utils.process import (
    create_process_executor,
    is_ci,
    run as run_command,
    run_process_jobs,
)
from scripts.feature.apply import patch_font_feature
from scripts.font_ops.glyphs import (
    FontmakeBranchJob,
    SourceStyle,
    compile_fontmake_branches,
    materialize_prepared_source,
    prepare_designspace_source,
)
from scripts.font_ops.metadata import (
    fix_italic_metadata,
    set_monospace_metadata,
    strip_name_whitespace,
)
from scripts.font_ops.merge import merge_ttfonts
from scripts.font_ops.metrics import adjust_line_height, verify_glyph_width
from scripts.font_ops.names import (
    get_unique_identifier,
    parse_style_name,
    update_font_names,
)
from scripts.font_ops.opentype import (
    add_ital_axis_to_stat,
    alias_codepoints,
)


FONT_VERSION = "v7.9"
# =========================================================================================


@dataclass(frozen=True)
class StaticPostprocessJob:
    input_path: str
    output_dir: str
    font_config: ResolvedBuildConfig
    runtime_context: BuildRuntimeContext


@dataclass(frozen=True)
class FontmakeSourceJob:
    source_path: str
    style: SourceStyle
    workspace: str
    target_width: int | None
    original_ref_width: int
    weight_mapping: dict[str, int]
    line_height: float


@dataclass(frozen=True)
class PreparedFontmakeSource:
    style: SourceStyle
    designspace_path: str
    vertical_metric: tuple[int, int]


@dataclass(frozen=True)
class VariablePostprocessJob:
    raw_path: str
    style: SourceStyle
    font_config: ResolvedBuildConfig
    runtime_context: BuildRuntimeContext


@dataclass(frozen=True)
class FontmakeBuildContext:
    temp_path: Path
    raw_variable_dir: Path
    raw_ttf_dir: Path
    raw_otf_dir: Path
    sources: tuple[PreparedFontmakeSource, ...]
    width_transform: tuple[int, int] | None = None


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


def postprocess_static_font(
    input_path: str | Path,
    output_dir: str | Path,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
) -> Path:
    source_path = Path(input_path)
    logger.debug("Postprocess static font: source=%s", source_path.name)
    font = TTFont(source_path, recalcTimestamp=False)
    is_ttf = source_path.suffix.lower() == ".ttf"
    fix_italic_metadata(font)
    set_monospace_metadata(font)
    strip_name_whitespace(font)

    style_compact = source_path.stem.split("-")[-1]

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

    # Preserve the established intermediate weight classes used by Maple Mono.
    if style_with_prefix_space == " Thin":
        font.table("OS/2").usWeightClass = 250
    elif style_with_prefix_space == " ExtraLight":
        font.table("OS/2").usWeightClass = 275

    if font_config.line_height != 1:
        adjust_line_height(
            font,
            font_config.line_height,
            runtime_context.resolved_vertical_metric,
        )

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
    alias_codepoints(font, font_config.codepoint_alias)

    verify_glyph_width(
        font=font,
        expect_widths=font_config.get_valid_glyph_width_list(),
        file_name=postscript_name,
    )

    if not is_ttf:
        font["CFF "].cff.topDictIndex[0].version = font_config.version

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{postscript_name}{source_path.suffix.lower()}"
    try:
        font.save(target_path)
    finally:
        font.close()
    return target_path


def postprocess_static_font_job(job: StaticPostprocessJob) -> None:
    set_log_task(Path(job.input_path).suffix.removeprefix(".").lower())
    target_path = postprocess_static_font(
        job.input_path,
        job.output_dir,
        job.font_config,
        job.runtime_context,
    )
    logger.info("Saved static font to %s", target_path)


def build_fontmake_source_job(job: FontmakeSourceJob) -> PreparedFontmakeSource:
    set_log_task("prepare")
    logger.info("Preparing %s", Path(job.source_path).name)
    prepared = prepare_designspace_source(
        job.source_path,
        job.style,
        target_width=job.target_width,
        original_ref_width=job.original_ref_width,
        weight_mapping=job.weight_mapping,
        line_height=job.line_height,
    )
    return PreparedFontmakeSource(
        job.style,
        str(materialize_prepared_source(prepared, job.workspace)),
        prepared.vertical_metric,
    )


def build_mono_autohint(
    f: str, font_config: ResolvedBuildConfig, runtime_context: BuildRuntimeContext
):
    style_compact = f.split("-")[-1].split(".")[0]
    postscript_name = f"{font_config.family_name_compact}-{style_compact}"
    logger.info("Auto-hinting %s.ttf", postscript_name)

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
    head = font.table("head")
    head.flags |= 1 << 2 | 1 << 3

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
    options.update(get_ttfautohint_options(font_config.ttfautohint_param))

    ttfautohint(**options)


def build_mono_autohint_job(job: MonoAutohintJob) -> None:
    set_log_task("ttf-autohint")
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
    logger.info(
        "Build Nerd Font variant: source=%s, suffix=%s",
        f,
        font_config.get_nf_suffix(),
    )
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
    logger.info("Saved Nerd Font to %s", target_path)


def build_nf_job(job: NerdFontBuildJob) -> None:
    set_log_task("nerd-font")
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


def prepare_fontmake_sources(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    executor: Executor | None = None,
) -> FontmakeBuildContext:
    """Prepare committed Designspace/UFO sources for later format tasks."""
    log_task("prepare", "Preparing font sources")
    source_dir = Path(runtime_context.src_dir)
    temp_path = Path(runtime_context.output_dir) / "temp"
    raw_variable_dir = temp_path / "variable"
    raw_ttf_dir = temp_path / "ttf"
    raw_otf_dir = temp_path / "otf"
    source_specs: tuple[tuple[Path, SourceStyle], ...] = (
        (
            source_dir / "MapleMono[wght].designspace",
            "regular",
        ),
        (
            source_dir / "MapleMono-Italic[wght].designspace",
            "italic",
        ),
    )

    shutil.rmtree(temp_path, ignore_errors=True)
    temp_path.mkdir(parents=True)
    target_width = (
        font_config.get_target_width() if font_config.get_width_name() else None
    )
    jobs = [
        FontmakeSourceJob(
            source_path=str(source_path),
            style=style,
            workspace=str(temp_path / "prepared" / style),
            target_width=target_width,
            original_ref_width=font_config.glyph_width,
            weight_mapping=font_config.weight_mapping,
            line_height=font_config.line_height,
        )
        for source_path, style in source_specs
    ]
    try:
        if executor is None:
            with create_process_executor(
                max_workers=len(jobs),
                fallback_to_threads=True,
            ) as process_executor:
                prepared_sources = tuple(
                    process_executor.map(build_fontmake_source_job, jobs)
                )
        else:
            prepared_sources = tuple(executor.map(build_fontmake_source_job, jobs))
        if font_config.line_height != 1:
            regular_source = next(
                source for source in prepared_sources if source.style == "regular"
            )
            runtime_context.resolved_vertical_metric = regular_source.vertical_metric
    except Exception:
        shutil.rmtree(temp_path, ignore_errors=True)
        raise

    return FontmakeBuildContext(
        temp_path,
        raw_variable_dir,
        raw_ttf_dir,
        raw_otf_dir,
        prepared_sources,
        (target_width, font_config.glyph_width) if target_width is not None else None,
    )


def compile_fontmake_formats(
    context: FontmakeBuildContext,
    build_formats: tuple[Literal["variable", "ttf", "otf"], ...],
    executor: Executor | None = None,
    *,
    target_styles: list[str] | None = None,
) -> None:
    """Compile all requested Fontmake branches in one shared job batch."""
    log_task("fontmake", "Building %s fonts via `fontmake`", ", ".join(build_formats))
    static_interpolate: bool | str = True
    if target_styles is not None:
        style_pattern = "|".join(re.escape(style) for style in target_styles)
        static_interpolate = rf".* (?:{style_pattern})"

    compile_fontmake_branches(
        [
            FontmakeBranchJob(
                designspace_path=Path(source.designspace_path),
                output=build_format,
                target=(
                    context.raw_variable_dir / f"{source.style}.ttf"
                    if build_format == "variable"
                    else {
                        "ttf": context.raw_ttf_dir,
                        "otf": context.raw_otf_dir,
                    }[build_format]
                ),
                interpolate=(
                    False if build_format == "variable" else static_interpolate
                ),
                source_label=source.style,
                width_transform=context.width_transform,
            )
            for build_format in build_formats
            for source in context.sources
        ],
        use_processes=True,
        executor=executor,
    )


def postprocess_variable_font_job(
    job: VariablePostprocessJob,
) -> None:
    """Postprocess one variable font after the parallel Fontmake compilation."""
    set_log_task("variable")
    raw_path = Path(job.raw_path)
    logger.debug("Postprocess variable font: source=%s", raw_path.name)
    is_italic = job.style == "italic"
    file_name = job.font_config.family_name_compact
    if is_italic:
        file_name += "-Italic"
    output_name = f"{file_name}[wght].ttf"
    font = TTFont(raw_path)
    try:
        patch_font_feature(
            config=job.font_config,
            font=font,
            issue_fea_dir=job.runtime_context.output_dir,
            is_italic=is_italic,
            is_cn=False,
            is_variable=True,
            is_hinted=False,
            fea_path=job.runtime_context.feature_file_path(is_italic),
        )

        style_name = "Italic" if is_italic else "Regular"
        postscript_name = f"{job.font_config.family_name_compact}-{style_name}"
        update_font_names(
            font=font,
            family_name=job.font_config.family_name,
            style_name=style_name,
            full_name=f"{job.font_config.family_name} {style_name}",
            version_str=job.font_config.version_str,
            postscript_name=postscript_name,
            unique_identifier=get_unique_identifier(
                font_config=job.font_config,
                postscript_name=postscript_name,
                variable=True,
            ),
            is_skip_subfamily=True,
        )

        if is_italic:
            add_ital_axis_to_stat(font)
        alias_codepoints(font, job.font_config.codepoint_alias)

        verify_glyph_width(
            font=font,
            expect_widths=job.font_config.get_valid_glyph_width_list(),
            file_name=output_name,
        )
        output_dir = Path(job.runtime_context.output_variable)
        output_dir.mkdir(parents=True, exist_ok=True)
        variable_path = output_dir / output_name
        font.save(variable_path)
        logger.info("Saved variable font to %s", variable_path)
    finally:
        font.close()


def build_variable_fonts(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    context: FontmakeBuildContext,
    executor: Executor | None = None,
) -> None:
    """Postprocess all compiled variable outputs in parallel."""
    jobs = [
        VariablePostprocessJob(
            raw_path=str(context.raw_variable_dir / f"{source.style}.ttf"),
            style=source.style,
            font_config=font_config,
            runtime_context=runtime_context,
        )
        for source in context.sources
    ]
    if executor is None:
        with create_process_executor(
            max_workers=len(jobs),
            fallback_to_threads=True,
        ) as process_executor:
            list(process_executor.map(postprocess_variable_font_job, jobs))
    else:
        list(executor.map(postprocess_variable_font_job, jobs))


def build_static_fonts(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    context: FontmakeBuildContext,
    build_format: Literal["ttf", "otf"],
    target_styles: list[str] | None,
    executor: Executor | None = None,
) -> None:
    """Postprocess one compiled static output format."""
    output_dir = Path(
        runtime_context.output_ttf
        if build_format == "ttf"
        else runtime_context.output_otf
    )
    raw_dir = context.raw_ttf_dir if build_format == "ttf" else context.raw_otf_dir
    static_jobs = [
        StaticPostprocessJob(
            input_path=str(font_path),
            output_dir=str(output_dir),
            font_config=font_config,
            runtime_context=runtime_context,
        )
        for font_path in sorted(raw_dir.glob(f"*.{build_format}"))
        if is_target_style_file(font_path.name, target_styles)
    ]
    run_process_jobs(
        font_config.pool_size,
        postprocess_static_font_job,
        static_jobs,
        executor,
    )


def ensure_cjk_variable_fonts(
    entry: ResolvedCJKBuildEntry,
    github_mirror: str,
    executor: Executor | None = None,
) -> tuple[Path, Path] | None:
    preset_config = entry.build_config
    regular_path = preset_config.output.dir / preset_config.output.regular_variable
    italic_path = preset_config.output.dir / preset_config.output.italic_variable

    if (
        not entry.common_options.clean_cache
        and regular_path.exists()
        and italic_path.exists()
    ):
        logger.info(
            "Reuse cached CJK variable fonts: locale=%s, regular=%s, italic=%s",
            entry.display_name,
            regular_path.name,
            italic_path.name,
        )
        return regular_path, italic_path

    try:
        build_cjk_fonts(
            preset_config,
            vf_only=True,
            executor=executor,
            github_mirror=github_mirror,
        )
    except FileNotFoundError as error:
        logger.warning(
            "Skip CJK output: locale=%s, reason=%s", entry.display_name, error
        )
        return None

    if not regular_path.exists() or not italic_path.exists():
        logger.warning(
            "Skip CJK output: locale=%s, reason=variable fonts were not generated",
            entry.display_name,
        )
        return None
    return regular_path, italic_path


def build_cjk_extended_variable_fonts(
    entry: ResolvedCJKBuildEntry,
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    output_dir: Path,
    executor: Executor | None = None,
) -> tuple[Path, Path] | None:
    base_variable_paths = ensure_cjk_variable_fonts(
        entry,
        runtime_context.effective_github_mirror,
        executor,
    )
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
            logger.warning("Core variable font not found: path=%s", base_path)
            return None
        if not extra_path.exists():
            logger.warning("CJK variable font not found: path=%s", extra_path)
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
            logger.debug(
                "Merge CJK variable font: locale=%s, glyphs_added=%s, unicodes_added=%s",
                entry.display_name,
                len(added_glyphs),
                added_codepoints,
            )
            merged_font.save(output_path)
            logger.info("Saved merged variable font to %s", output_path)
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
                logger.info(
                    "Instantiate CJK static font: locale=%s, style=%s",
                    entry.display_name,
                    style_compact,
                )
                static_font = instantiate_variable_font(
                    var_font,
                    {"wght": instance.coordinate},
                    static=True,
                    downgrade_cff2="CFF2" in var_font,
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
                    output_path = output_dir / f"{postscript_name}.ttf"
                    static_font.save(output_path)
                    logger.info("Saved CJK static font to %s", output_path)
                finally:
                    static_font.close()
        finally:
            var_font.close()

    if entry.common_options.use_hinted:
        logger.info("Auto-hint CJK static fonts: locale=%s", entry.display_name)
        autohint_static_fonts(output_dir, font_config.ttfautohint_param)

    return output_dir


def merge_cached_cjk_static_font_job(job: CJKStaticMergeJob) -> None:
    set_log_task(job.entry.locale_name.lower())
    logger.debug(
        "Merge cached CJK static font: locale=%s, style=%s",
        job.entry.display_name,
        job.style_compact,
    )
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
        output_path = Path(job.output_dir) / f"{postscript_name}.ttf"
        static_font.save(output_path)
        logger.info("Saved CJK static font to %s", output_path)
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
    executor: Executor | None = None,
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

    logger.info(
        "Use cached CJK static fonts: locale=%s, source=%s, path=%s",
        entry.display_name,
        resolved_base.source_kind,
        resolved_base.static_dir,
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
        executor,
    )

    if entry.common_options.use_hinted:
        logger.info("Auto-hint CJK static fonts: locale=%s", entry.display_name)
        for profile, _ in profile_core_fonts:
            autohint_static_fonts(
                static_output_dir(
                    runtime_context.output_dir,
                    profile.output_locale,
                ),
                font_config.ttfautohint_param,
            )

    return True


def build_cjk_extended_outputs(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
    executor: Executor | None = None,
) -> None:
    if font_config.cjk_output_format == "variable":
        build_cjk_extended_variable_outputs(font_config, runtime_context, executor)
    else:
        build_cjk_extended_static_outputs(
            font_config, runtime_context, target_styles, executor
        )


def build_cjk_extended_variable_outputs(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    executor: Executor | None = None,
) -> None:
    entries = font_config.get_selected_cjk_entries()
    if not entries:
        logger.warning("Skip CJK outputs: reason=no CJK locale selected")
        return

    built_any = False
    for entry in entries:
        log_task(entry.locale_name.lower(), "Building CJK variable outputs")
        try:
            merged_paths = build_cjk_extended_variable_fonts(
                entry,
                font_config,
                runtime_context,
                variable_output_dir(runtime_context.output_dir, entry.locale_name),
                executor,
            )
        except FileNotFoundError as error:
            logger.warning(
                "Skip CJK output: locale=%s, reason=%s",
                entry.display_name,
                error,
            )
            continue
        if merged_paths is not None:
            built_any = True

    runtime_context.is_cjk_built = built_any
    if not built_any:
        logger.warning(
            "Skip CJK outputs: locales=%s, mode=%s, reason=all selected locale builds failed",
            ",".join(entry.locale_name for entry in entries),
            font_config.cjk_output_format,
        )


def build_cjk_extended_static_outputs(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
    executor: Executor | None = None,
) -> None:
    entries = font_config.get_selected_cjk_entries()
    if not entries:
        logger.warning("Skip CJK outputs: reason=no CJK locale selected")
        return

    temp_root = Path(runtime_context.output_dir) / ".cjk-temp"
    built_any = False
    for entry in entries:
        log_task(entry.locale_name.lower(), "Building CJK static outputs")
        try:
            built_from_cache = build_cjk_extended_static_fonts_from_cache(
                entry,
                font_config,
                runtime_context,
                target_styles,
                executor,
            )
        except FileNotFoundError as error:
            logger.warning(
                "Skip CJK output: locale=%s, reason=%s",
                entry.display_name,
                error,
            )
            continue
        if built_from_cache:
            built_any = True
            continue

        locale_output_dir = temp_root / entry.locale_name.upper()
        try:
            merged_paths = build_cjk_extended_variable_fonts(
                entry,
                font_config,
                runtime_context,
                locale_output_dir,
                executor,
            )
        except FileNotFoundError as error:
            logger.warning(
                "Skip CJK output: locale=%s, reason=%s",
                entry.display_name,
                error,
            )
            continue
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
    if not built_any:
        logger.warning(
            "Skip CJK outputs: locales=%s, mode=%s, reason=all selected locale builds failed",
            ",".join(entry.locale_name for entry in entries),
            font_config.cjk_output_format,
        )


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
    executor: Executor | None = None,
):
    """Generate hinted TTF derivatives from production static TTF fonts."""
    log_task("ttf-autohint", "Auto-hint static fonts")
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
        executor,
    )


def build_woff2_fonts(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    executor: Executor | None = None,
) -> None:
    """Convert the generated static TTF fonts to WOFF2 in a dedicated task."""
    log_task("woff2", "Converting static fonts to WOFF2")
    convert_to_web(
        runtime_context.output_ttf,
        output_dir=runtime_context.output_woff2,
        flavor="woff2",
        executor=executor,
    )


def build_nerd_fonts(
    font_config: ResolvedBuildConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
    executor: Executor | None = None,
):
    """Build Nerd Font variants."""
    if not font_config.nerd_font.enable:
        return

    log_task("nerd-font", "Build Nerd Font outputs")

    makedirs(runtime_context.output_nf, exist_ok=True)
    use_font_patcher = runtime_context.should_use_font_patcher(font_config)
    runtime_context.ensure_font_patcher_available(font_config)

    _version = font_config.nerd_font.version
    logger.info(
        "Patch Nerd Font: version=%s, method=%s",
        _version,
        "Font Patcher" if use_font_patcher else "prebuilt base font",
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
        executor,
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
        self.start_build_timer()
        self.prepare_output_root()

        with create_process_executor(
            max_workers=max(self.font_config.pool_size, 2),
            fallback_to_threads=True,
        ) as process_executor:
            if self.should_build_base_outputs():
                fontmake_context = prepare_fontmake_sources(
                    self.font_config,
                    self.runtime_context,
                    process_executor,
                )
                try:
                    fontmake_formats: tuple[Literal["variable", "ttf", "otf"], ...] = (
                        ("variable", "ttf", "otf")
                        if (
                            self.font_config.wants_format("otf")
                            and not self.font_config.debug
                        )
                        else ("variable", "ttf")
                    )
                    compile_fontmake_formats(
                        fontmake_context,
                        fontmake_formats,
                        process_executor,
                        target_styles=self.target_styles,
                    )
                    build_variable_fonts(
                        self.font_config,
                        self.runtime_context,
                        fontmake_context,
                        process_executor,
                    )
                    build_static_fonts(
                        self.font_config,
                        self.runtime_context,
                        fontmake_context,
                        "ttf",
                        self.target_styles,
                        process_executor,
                    )
                    if (
                        self.font_config.wants_format("otf")
                        and not self.font_config.debug
                    ):
                        build_static_fonts(
                            self.font_config,
                            self.runtime_context,
                            fontmake_context,
                            "otf",
                            self.target_styles,
                            process_executor,
                        )
                finally:
                    shutil.rmtree(fontmake_context.temp_path, ignore_errors=True)
                if self.font_config.needs_hinted_ttf():
                    build_base_fonts(
                        self.font_config,
                        self.runtime_context,
                        self.target_styles,
                        process_executor,
                    )
                if self.should_build_woff2_outputs():
                    build_woff2_fonts(
                        self.font_config,
                        self.runtime_context,
                        process_executor,
                    )
                elif self.font_config.wants_format("woff2"):
                    log_task("woff2", "Skipping WOFF2 conversion for a debug build")
            else:
                self.reuse_base_output_cache()

            if self.should_build_nerd_fonts():
                build_nerd_fonts(
                    self.font_config,
                    self.runtime_context,
                    self.target_styles,
                    process_executor,
                )
            else:
                log_task("nerd-font", "Skipping Nerd Font outputs")

            if self.should_build_cjk_outputs():
                if self.should_persist_cjk_variable_outputs():
                    build_cjk_extended_variable_outputs(
                        self.font_config,
                        self.runtime_context,
                        process_executor,
                    )
                else:
                    build_cjk_extended_static_outputs(
                        self.font_config,
                        self.runtime_context,
                        self.target_styles,
                        process_executor,
                    )
            else:
                set_log_task("cjk")
                logger.warning("Skip CJK outputs: reason=no CJK locale selected")

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
            logger.info("Clean build cache")
            shutil.rmtree(self.runtime_context.output_dir, ignore_errors=True)
            shutil.rmtree(self.runtime_context.output_woff2, ignore_errors=True)
        ensure_base_output_dirs(self.runtime_context)

    def start_build_timer(self) -> None:
        self.start_time = time.time()
        set_log_task("system")
        cjk_entries = self.font_config.get_selected_cjk_entries()
        cjk_summary = "disabled"
        if cjk_entries:
            locales = ", ".join(entry.display_name for entry in cjk_entries)
            cjk_summary = f"{self.font_config.cjk_output_format} ({locales})"
        details = [
            f"{self.font_config.family_name} ({self.font_config.version_str})",
            f"Formats: {', '.join(item.upper() for item in self.font_config.formats)}",
            f"Styles: {', '.join(self.target_styles) if self.target_styles else 'all'}",
            f"Hinting: {'enabled' if self.font_config.use_hinted else 'disabled'}",
            f"Ligatures: {'enabled' if self.font_config.enable_ligature else 'disabled'}",
            f"Nerd Font: {'enabled' if self.font_config.nerd_font.enable else 'disabled'}",
            f"CJK: {cjk_summary}",
            f"Cache: {'enabled' if self.font_config.cache else 'disabled'}",
            f"Archive: {'enabled' if self.font_config.archive else 'disabled'}",
            f"Line height: {self.font_config.line_height:g}",
        ]
        if self.font_config.width != "default":
            details.insert(
                5,
                "Width: "
                f"{self.font_config.width} "
                f"({self.font_config.glyph_width} -> "
                f"{self.font_config.get_target_width()}, "
                f"suffix {self.font_config.get_width_name()})",
            )
        logger.info("Build started: %s", " | ".join(details))

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
        logger.info("Reuse cached Variable, TTF, and TTF-AutoHint outputs")

    def should_build_nerd_fonts(self) -> bool:
        return self.font_config.nerd_font.enable

    def should_build_cjk_outputs(self) -> bool:
        return bool(self.font_config.get_selected_cjk_entries())

    def should_build_woff2_outputs(self) -> bool:
        return self.font_config.wants_format("woff2") and not self.font_config.debug

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
        log_task("archive", "Archive build outputs")
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

            logger.info("Archived %s", file_name)

    def finish_build(self) -> None:
        set_log_task("system")
        freeze_str = (
            self.font_config.freeze_config_str
            if self.font_config.freeze_config_str != ""
            else "default config"
        )
        time_diff = time.time() - self.start_time
        output_root = Path(self.runtime_context.output_dir).resolve()
        outputs = (
            sorted(
                path.name
                for path in output_root.iterdir()
                if path.is_dir()
                and path.name not in {".cjk-temp", "temp", "build-config.json"}
            )
            if output_root.exists()
            else []
        )
        cjk_locales = (
            ",".join(
                entry.locale_name
                for entry in self.font_config.get_selected_cjk_entries()
            )
            or "none"
        )
        logger.info(
            "Build finished: duration=%.2fs, family=%s, resolved_width=%s, fea=%s, outputs=%s, nerd_font_built=%s, cjk_locales=%s, cjk_built=%s, output_root=%s",
            time_diff,
            self.font_config.family_name,
            self.font_config.get_target_width(),
            freeze_str,
            ",".join(outputs) or "none",
            self.runtime_context.is_nf_built,
            cjk_locales,
            self.runtime_context.is_cjk_built,
            output_root,
        )


def run(parsed_args, version: str | None = None):
    global FONT_VERSION
    try:
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
    except BuildDependencyError as error:
        logger.error("Build failed: %s", error)
        raise SystemExit(1) from error


def main(args: list[str] | None = None, version: str | None = None) -> None:
    from scripts.config.cli import parse_args

    parsed_args = parse_args(args, version=version)
    use_debug_log_default = parsed_args.debug and ENVIRONMENT_VARIABLE not in environ
    if use_debug_log_default:
        environ[ENVIRONMENT_VARIABLE] = "DEBUG"
    try:
        configure_logging()
        run(parsed_args, version=version)
    finally:
        if use_debug_log_default:
            del environ[ENVIRONMENT_VARIABLE]

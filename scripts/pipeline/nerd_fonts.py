from __future__ import annotations

from concurrent.futures import Executor
from dataclasses import dataclass
from os import makedirs, path, remove
from pathlib import Path
from typing import Callable

from scripts.config.base import ResolvedConfig
from scripts.config.runtime import BuildRuntimeContext
from scripts.font_ops.fonttools import TTFont, save_font_atomic
from scripts.font_ops.glyph_transform import smart_change_width
from scripts.font_ops.merge import merge_ttfonts
from scripts.font_ops.metrics import adjust_line_height, verify_glyph_width
from scripts.font_ops.names import parse_style_name, update_font_names
from scripts.pipeline.artifacts import collect_build_files, prune_build_files
from scripts.utils.downloads import check_font_patcher
from scripts.utils.errors import BuildDependencyError
from scripts.utils.files import join_path
from scripts.utils.logging import (
    log_task,
    logger,
    log_task_complete,
    set_log_task,
)
from scripts.utils.process import run as run_command, run_process_jobs


@dataclass(frozen=True)
class NerdFontBuildJob:
    font_basename: str
    use_font_patcher: bool
    font_config: ResolvedConfig
    runtime_context: BuildRuntimeContext


def should_use_font_patcher(config: ResolvedConfig) -> bool:
    return bool(
        config.nerd_font.extra_args
        or config.nerd_font.use_font_patcher
        or config.nerd_font.glyphs != ["--complete"]
    )


def ensure_font_patcher_available(
    config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
) -> None:
    if not should_use_font_patcher(config):
        return
    if not runtime_context.font_forge_bin or not path.exists(
        runtime_context.font_forge_bin
    ):
        raise BuildDependencyError(
            f"FontForge bin ({runtime_context.font_forge_bin}) not found, "
            "cannot build with Nerd Font Patcher"
        )
    if not check_font_patcher(
        version=config.nerd_font.version,
        github_mirror=runtime_context.effective_github_mirror,
    ):
        raise BuildDependencyError(
            "Nerd Font Patcher assets are unavailable for the requested version"
        )


def build_nf_by_prebuild_nerd_font(
    font_basename: str,
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
) -> TTFont:
    variant = font_config.get_nf_variant()
    nf_base_font_path = str(variant.base_path(runtime_context.src_dir))
    temporary_path = None
    if font_config.get_width_name():
        temporary_font = TTFont(nf_base_font_path)
        try:
            smart_change_width(
                font=temporary_font,
                target_width=font_config.get_target_width(),
                original_ref_width=font_config.glyph_width,
                also_scale_y=True,
            )
            temporary_path = f"{runtime_context.output_dir}/NF-Base-{font_basename}"
            save_font_atomic(temporary_font, temporary_path)
        finally:
            temporary_font.close()

    try:
        return merge_ttfonts(
            base_font_path=join_path(runtime_context.ttf_base_dir, font_basename),
            extra_font_path=temporary_path or nf_base_font_path,
        )
    finally:
        if temporary_path is not None:
            remove(temporary_path)


def build_nf_by_font_patcher(
    font_basename: str,
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
) -> TTFont:
    """Patch a base font with FontPatcher and return the generated font."""
    if runtime_context.font_forge_bin is None:
        raise BuildDependencyError(
            "FontForge bin is unavailable after dependency validation"
        )
    patcher_args = [
        runtime_context.font_forge_bin,
        "FontPatcher/font-patcher",
        "-l",
        "--careful",
        "--outputdir",
        runtime_context.output_nf,
        *font_config.nerd_font.glyphs,
    ]
    if font_config.nerd_font.propo:
        patcher_args.append("--variable-width-glyphs")
    elif font_config.nerd_font.mono:
        patcher_args.append("--mono")
    patcher_args.extend(font_config.nerd_font.extra_args)
    patcher_args.append(join_path(runtime_context.ttf_base_dir, font_basename))
    run_command(patcher_args)

    variant = font_config.get_nf_variant()
    generated_path = str(
        variant.patched_font_path(runtime_context.output_nf, font_basename)
    )
    font = TTFont(generated_path)
    remove(generated_path)
    if "nonmarkingreturn" in font.getGlyphNames():
        font["hmtx"]["nonmarkingreturn"] = (600, 0)
    return font


def build_nf(
    font_basename: str,
    load_source: Callable[[str, ResolvedConfig, BuildRuntimeContext], TTFont],
    use_font_patcher: bool,
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
) -> Path:
    logger.debug(
        "Build Nerd Font variant: source=%s, suffix=%s",
        font_basename,
        font_config.get_nf_variant().suffix,
    )
    font = load_source(font_basename, font_config, runtime_context)
    try:
        style_compact = font_basename.split("-")[-1].split(".")[0]
        (
            style_prefix,
            legacy_style,
            preferred_style,
            skip_subfamily,
            _,
        ) = parse_style_name(style_name_compact=style_compact)
        symbol = font_config.get_nf_variant().symbol
        postscript_name = f"{font_config.family_name_compact}-{symbol}-{style_compact}"
        update_font_names(
            font=font,
            font_config=font_config,
            family_name=f"{font_config.family_name} {symbol}{style_prefix}",
            style_name=legacy_style,
            full_name=f"{font_config.family_name} {symbol} {preferred_style}",
            postscript_name=postscript_name,
            is_skip_subfamily=skip_subfamily,
            preferred_family_name=f"{font_config.family_name} {symbol}",
            preferred_style_name=preferred_style,
        )
        if font_config.line_height != 1:
            adjust_line_height(
                font,
                font_config.line_height,
                runtime_context.resolved_vertical_metric,
            )
        if not (use_font_patcher or font_config.get_nf_suffix() == "Propo"):
            verify_glyph_width(
                font=font,
                expect_widths=font_config.get_valid_glyph_width_list(),
                file_name=postscript_name,
            )
        target_path = Path(runtime_context.output_nf) / (f"{postscript_name}.ttf")
        save_font_atomic(font, target_path)
        logger.info("Saved Nerd Font to %s", target_path)
    finally:
        font.close()
    return target_path


def build_nf_job(job: NerdFontBuildJob) -> Path:
    set_log_task("nerd-font")
    load_source = (
        build_nf_by_font_patcher
        if job.use_font_patcher
        else build_nf_by_prebuild_nerd_font
    )
    return build_nf(
        job.font_basename,
        load_source,
        job.use_font_patcher,
        job.font_config,
        job.runtime_context,
    )


def build_nerd_fonts(
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
    executor: Executor | None = None,
) -> list[Path]:
    """Build configured Nerd Font variants."""
    if not font_config.nerd_font.enable:
        return []

    started_at = log_task("nerd-font", "Build Nerd Font outputs")
    makedirs(runtime_context.output_nf, exist_ok=True)
    use_font_patcher = should_use_font_patcher(font_config)
    ensure_font_patcher_available(font_config, runtime_context)
    logger.debug(
        "Patch Nerd Font: version=%s, method=%s",
        font_config.nerd_font.version,
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
    output_paths = run_process_jobs(
        font_config.pool_size,
        build_nf_job,
        jobs,
        executor,
    )
    runtime_context.is_nf_built = True
    log_task_complete(started_at, f"{len(output_paths)} fonts")
    return output_paths

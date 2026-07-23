from __future__ import annotations

from concurrent.futures import Executor
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from ttfautohint import ttfautohint

from scripts.cjk.builder import get_ttfautohint_options
from scripts.config.base import ResolvedConfig
from scripts.config.runtime import BuildRuntimeContext
from scripts.feature.apply import patch_font_feature
from scripts.font_ops.conversion import convert_to_web
from scripts.font_ops.fonttools import TTFont
from scripts.pipeline.artifacts import collect_build_files
from scripts.utils.files import join_path
from scripts.utils.logging import (
    log_task,
    logger,
    log_task_complete,
    set_log_task,
)
from scripts.utils.process import run_process_jobs


@dataclass(frozen=True)
class MonoAutohintJob:
    font_basename: str
    font_config: ResolvedConfig
    runtime_context: BuildRuntimeContext


def build_mono_autohint(
    font_basename: str,
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
) -> Path:
    style_compact = font_basename.split("-")[-1].split(".")[0]
    postscript_name = f"{font_config.family_name_compact}-{style_compact}"
    logger.debug("Auto-hint font: %s.ttf", postscript_name)

    source_path = join_path(runtime_context.output_ttf, font_basename)
    font = TTFont(source_path)
    try:
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
        head = font.table("head")
        head.flags |= 1 << 2 | 1 << 3
        buffer = BytesIO()
        font.save(buffer)
    finally:
        font.close()

    output_path = Path(runtime_context.output_ttf_hinted) / f"{postscript_name}.ttf"
    options = {
        "in_buffer": buffer.getvalue(),
        "reference_file": join_path(
            runtime_context.output_ttf,
            f"{font_config.family_name_compact}-Regular.ttf",
        ),
        "out_file": str(output_path),
        "windows_compatibility": True,
    }
    options.update(get_ttfautohint_options(font_config.ttfautohint_param))
    ttfautohint(**options)
    logger.info("Saved hinted font to %s", output_path)
    return output_path


def build_mono_autohint_job(job: MonoAutohintJob) -> Path:
    set_log_task("ttf-autohint")
    return build_mono_autohint(
        job.font_basename,
        job.font_config,
        job.runtime_context,
    )


def build_base_fonts(
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
    target_styles: list[str] | None,
    executor: Executor | None = None,
) -> list[Path]:
    """Generate hinted TTF derivatives from production static TTF fonts."""
    started_at = log_task("ttf-autohint", "Hint static TTF")
    jobs = [
        MonoAutohintJob(
            font_basename=file_name,
            font_config=font_config,
            runtime_context=runtime_context,
        )
        for file_name in collect_build_files(
            runtime_context.output_ttf,
            target_styles,
        )
    ]
    output_paths = run_process_jobs(
        font_config.pool_size,
        build_mono_autohint_job,
        jobs,
        executor,
    )
    log_task_complete(started_at, f"{len(output_paths)} fonts")
    return output_paths


def build_woff2_fonts(
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
    executor: Executor | None = None,
) -> list[Path]:
    """Convert generated static TTF fonts to WOFF2."""
    started_at = log_task("woff2", "Convert static TTF to WOFF2")
    output_paths = convert_to_web(
        runtime_context.output_ttf,
        output_dir=runtime_context.output_woff2,
        flavor="woff2",
        executor=executor,
    )
    log_task_complete(started_at, f"{len(output_paths)} fonts")
    return output_paths

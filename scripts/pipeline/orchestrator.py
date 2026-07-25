#!/usr/bin/env python3
from __future__ import annotations

from concurrent.futures import Executor
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import time
from os import environ, listdir, makedirs
from typing import Any, Literal
from scripts.font_ops.fonttools import (
    TTFont,
)
from scripts.config.base import ResolvedCJKBuildEntry, ResolvedConfig
from scripts.cjk.resolver import serialize_cjk_build_config
from scripts.config.paths import (
    merged_variable_name,
    static_output_dir,
    variable_output_dir,
)
from scripts.utils.errors import BuildDependencyError
from scripts.config.resolver import BuildConfigResolver
from scripts.config.runtime import BuildRuntimeContext
from scripts.pipeline.cache import relative_cache_path
from scripts.utils.files import archive_fonts, join_path
from scripts.utils.logging import (
    ENVIRONMENT_VARIABLE,
    TaskName,
    configure_logging,
    log_task,
    log_task_complete,
    logger,
    set_log_task,
)
from scripts.utils.process import (
    SynchronousExecutor,
    create_process_executor,
    is_ci,
    run_process_jobs,
)
from scripts.utils.version import version_tag
from scripts.feature.apply import prepare_designspace_features
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
from scripts.font_ops.metrics import adjust_line_height, verify_glyph_width
from scripts.font_ops.names import parse_style_name, update_font_names
from scripts.font_ops.opentype import (
    add_ital_axis_to_stat,
    add_weight_axis_values_to_stat,
    alias_codepoints,
)
from scripts.pipeline.artifacts import (
    base_cache_identity,
    cleanup_unselected_base_formats,
    ensure_base_output_dirs,
    expected_static_font_paths,
    expected_static_styles,
    is_target_style_file,
    read_font_vertical_metric,
)
from scripts.pipeline.cache import (
    CACHE_SCHEMA,
    output_snapshot,
    read_cache_record,
    stage_identity,
    validate_stage,
    write_cache_record as persist_cache_record,
)
from scripts.pipeline.base_fonts import build_base_fonts, build_woff2_fonts
from scripts.pipeline.cjk_outputs import (
    build_cjk_extended_static_outputs,
    build_cjk_extended_variable_outputs,
)
from scripts.pipeline.nerd_fonts import build_nerd_fonts


@dataclass(frozen=True)
class StaticPostprocessJob:
    input_path: str
    output_dir: str
    font_config: ResolvedConfig
    runtime_context: BuildRuntimeContext


@dataclass(frozen=True)
class FontmakeSourceJob:
    source_path: str
    style: SourceStyle
    workspace: str
    feature_file_path: str
    issue_fea_dir: str
    font_config: ResolvedConfig
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
    font_config: ResolvedConfig
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
class BuildPlan:
    """Content stages and output policy derived from resolved configuration."""

    target_styles: list[str] | None
    required_base_formats: tuple[Literal["variable", "ttf", "otf"], ...]
    build_woff2: bool
    build_nerd_font: bool
    cjk_mode: Literal["variable", "static"] | None
    cleanup_base_static: bool
    archive: bool

    @classmethod
    def from_config(cls, config: ResolvedConfig) -> BuildPlan:
        if config.least_styles:
            target_styles = ["Regular", "Bold", "Italic", "BoldItalic"]
        elif config.debug:
            target_styles = ["Regular", "Italic"]
        else:
            target_styles = None

        base_formats: list[Literal["variable", "ttf", "otf"]] = ["variable"]
        if (
            config.wants_format("ttf")
            or config.wants_format("woff2")
            or config.needs_hinted_ttf()
        ):
            base_formats.append("ttf")
        if config.wants_format("otf") and not config.debug:
            base_formats.append("otf")

        cjk_mode: Literal["variable", "static"] | None = None
        if config.get_selected_cjk_entries():
            cjk_mode = config.cjk_output_format

        return cls(
            target_styles=target_styles,
            required_base_formats=tuple(base_formats),
            build_woff2=config.wants_format("woff2") and not config.debug,
            build_nerd_font=config.nerd_font.enable,
            cjk_mode=cjk_mode,
            cleanup_base_static=not config.wants_format("ttf"),
            archive=config.archive,
        )


def postprocess_static_font(
    input_path: str | Path,
    output_dir: str | Path,
    font_config: ResolvedConfig,
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
        font_config=font_config,
        family_name=font_config.family_name + style_with_prefix_space,
        style_name=style_in_2,
        full_name=f"{font_config.family_name} {style_in_17}",
        postscript_name=postscript_name,
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


def postprocess_static_font_job(job: StaticPostprocessJob) -> Path:
    set_log_task(Path(job.input_path).suffix.removeprefix(".").lower())
    target_path = postprocess_static_font(
        job.input_path,
        job.output_dir,
        job.font_config,
        job.runtime_context,
    )
    logger.info("Saved static font to %s", target_path)
    return target_path


def build_fontmake_source_job(job: FontmakeSourceJob) -> PreparedFontmakeSource:
    set_log_task("prepare")
    logger.debug("Prepare source: %s", Path(job.source_path).name)
    prepared = prepare_designspace_source(
        job.source_path,
        job.style,
        target_width=job.target_width,
        original_ref_width=job.original_ref_width,
        weight_mapping=job.weight_mapping,
        line_height=job.line_height,
    )
    prepare_designspace_features(
        job.font_config,
        prepared.designspace,
        issue_fea_dir=job.issue_fea_dir,
        is_italic=job.style == "italic",
        fea_path=job.feature_file_path,
    )
    return PreparedFontmakeSource(
        job.style,
        str(materialize_prepared_source(prepared, job.workspace)),
        prepared.vertical_metric,
    )


def prepare_fontmake_sources(
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
    executor: Executor | None = None,
) -> FontmakeBuildContext:
    """Prepare committed Designspace/UFO sources for later format tasks."""
    started_at = log_task(TaskName.PREPARE, "Prepare font sources")
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
            feature_file_path=runtime_context.feature_file_path(style == "italic"),
            issue_fea_dir=runtime_context.output_dir,
            font_config=font_config,
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

    context = FontmakeBuildContext(
        temp_path,
        raw_variable_dir,
        raw_ttf_dir,
        raw_otf_dir,
        prepared_sources,
        (target_width, font_config.glyph_width) if target_width is not None else None,
    )
    log_task_complete(started_at, f"{len(prepared_sources)} sources")
    return context


def compile_fontmake_formats(
    context: FontmakeBuildContext,
    build_formats: tuple[Literal["variable", "ttf", "otf"], ...],
    executor: Executor | None = None,
    *,
    target_styles: list[str] | None = None,
) -> None:
    """Compile all requested Fontmake branches in one shared job batch."""
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
) -> Path:
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
        style_name = "Italic" if is_italic else "Regular"
        postscript_name = f"{job.font_config.family_name_compact}-{style_name}"
        update_font_names(
            font=font,
            font_config=job.font_config,
            family_name=job.font_config.family_name,
            style_name=style_name,
            full_name=f"{job.font_config.family_name} {style_name}",
            postscript_name=postscript_name,
            is_skip_subfamily=True,
            variable=True,
        )
        add_weight_axis_values_to_stat(font, italic=is_italic)

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
    return variable_path


def build_variable_fonts(
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
    context: FontmakeBuildContext,
    executor: Executor | None = None,
) -> list[Path]:
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
            return list(process_executor.map(postprocess_variable_font_job, jobs))
    return list(executor.map(postprocess_variable_font_job, jobs))


def build_static_fonts(
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
    context: FontmakeBuildContext,
    build_format: Literal["ttf", "otf"],
    target_styles: list[str] | None,
    executor: Executor | None = None,
) -> list[Path]:
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
    return run_process_jobs(
        font_config.pool_size,
        postprocess_static_font_job,
        static_jobs,
        executor,
    )


class MapleBuildPipeline:
    """Coordinate the Maple Mono build pipeline without crossing process boundaries."""

    def __init__(
        self,
        font_config: ResolvedConfig,
        runtime_context: BuildRuntimeContext,
    ) -> None:
        self.font_config = font_config
        self.runtime_context = runtime_context
        self.should_use_cache = font_config.cache
        self.plan = BuildPlan.from_config(font_config)
        self.target_styles = self.plan.target_styles
        self.start_time = 0.0
        self._cache_identity_checked = False
        self._cache_identity_valid = True
        self._cache_reuse_logged: set[str] = set()
        self._cache_record: dict[str, Any] | None = None
        self._build_identity: dict[str, object] | None = None

    def build(self) -> None:
        self.start_build_timer()
        self.prepare_output_root()
        self.write_build_config()

        process_executor = (
            SynchronousExecutor()
            if self.font_config.pool_size <= 1
            else create_process_executor(
                max_workers=self.font_config.pool_size,
                fallback_to_threads=True,
            )
        )
        with process_executor:
            base_formats = self.base_formats_to_build()
            self._build_base_outputs(base_formats, process_executor)
            self._build_derived_outputs(base_formats, process_executor)
            self._build_cjk_outputs(process_executor)

        if self.plan.cleanup_base_static:
            cleanup_unselected_base_formats(self.font_config, self.runtime_context)

        self.write_build_record()

        if self.plan.archive:
            self.archive_outputs()

        self.finish_build()

    def _build_base_outputs(
        self,
        base_formats: tuple[Literal["variable", "ttf", "otf"], ...],
        process_executor: Executor,
    ) -> None:
        if not base_formats:
            self.reuse_base_output_cache()
            return

        fontmake_context = prepare_fontmake_sources(
            self.font_config,
            self.runtime_context,
            process_executor,
        )
        try:
            format_labels = ", ".join(
                "Variable" if item == "variable" else item.upper()
                for item in base_formats
            )
            started_at = log_task(TaskName.FONTMAKE, "Build %s", format_labels)
            compile_fontmake_formats(
                fontmake_context,
                base_formats,
                process_executor,
                target_styles=self.target_styles,
            )
            output_counts: list[tuple[str, int]] = []
            if "variable" in base_formats:
                variable_paths = build_variable_fonts(
                    self.font_config,
                    self.runtime_context,
                    fontmake_context,
                    process_executor,
                )
                output_counts.append(("Variable", len(variable_paths or ())))
            for build_format in ("ttf", "otf"):
                if build_format in base_formats:
                    static_paths = build_static_fonts(
                        self.font_config,
                        self.runtime_context,
                        fontmake_context,
                        build_format,
                        self.target_styles,
                        process_executor,
                    )
                    output_counts.append(
                        (build_format.upper(), len(static_paths or ()))
                    )
            summary = ", ".join(f"{label}: {count}" for label, count in output_counts)
            log_task_complete(started_at, summary)
        finally:
            shutil.rmtree(fontmake_context.temp_path, ignore_errors=True)

    def _build_derived_outputs(
        self,
        base_formats: tuple[Literal["variable", "ttf", "otf"], ...],
        process_executor: Executor,
    ) -> None:
        ttf_paths = self._base_stage_expected_paths("ttf")
        hinted_paths = self._base_stage_expected_paths("ttf-autohint")
        if self.should_build_hinted_ttf(base_formats):
            hinted_paths = build_base_fonts(
                self.font_config,
                self.runtime_context,
                ttf_paths,
                process_executor,
            )
        if self.should_build_woff2_outputs(base_formats):
            build_woff2_fonts(
                ttf_paths,
                self.runtime_context,
                process_executor,
            )
        elif self.font_config.wants_format("woff2") and self.font_config.debug:
            set_log_task("woff2")
            logger.debug("Skip WOFF2 conversion for a debug build")

        if self.plan.build_nerd_font:
            if self._validate_recorded_stage("nf"):
                logger.info("Reuse cached NF outputs")
                self.runtime_context.is_nf_built = True
            else:
                nf_inputs = hinted_paths if self.font_config.use_hinted else ttf_paths
                build_nerd_fonts(
                    self.font_config,
                    self.runtime_context,
                    nf_inputs,
                    process_executor,
                )
        else:
            set_log_task("nerd-font")
            logger.debug("Skip Nerd Font outputs because the stage is disabled")

    def _cjk_stage_targets(
        self,
    ) -> list[tuple[str, ResolvedCJKBuildEntry, str]]:
        if not self.plan.cjk_mode:
            return []

        targets: list[tuple[str, ResolvedCJKBuildEntry, str]] = []
        for entry in self.font_config.get_selected_cjk_entries():
            if self.plan.cjk_mode == "variable":
                include_nf = (
                    self.font_config.nerd_font.enable
                    and entry.common_options.with_nerd_font
                )
            else:
                include_nf = (
                    self.runtime_context.is_nf_built
                    and entry.common_options.with_nerd_font
                )
            output_locales: list[str] = []
            if include_nf:
                output_locales.append(f"NF-{entry.locale_name}")
            if not include_nf or self.font_config.use_cjk_both:
                output_locales.append(entry.locale_name)
            for output_locale in output_locales:
                stage = f"{output_locale.lower()}-{self.plan.cjk_mode}"
                targets.append((stage, entry, output_locale))
        return targets

    def _cjk_stage_target(
        self,
        stage: str,
    ) -> tuple[ResolvedCJKBuildEntry, str]:
        for target_stage, entry, output_locale in self._cjk_stage_targets():
            if target_stage == stage:
                return entry, output_locale
        raise ValueError(f"Unknown CJK stage: {stage}")

    def _cjk_stage_expected_paths(self, output_locale: str) -> list[Path]:
        if self.plan.cjk_mode == "variable":
            directory = variable_output_dir(
                self.runtime_context.output_dir,
                output_locale,
            )
            locale_name = (
                output_locale[3:] if output_locale.startswith("NF-") else output_locale
            )
            prefix = f"{self.font_config.family_name_compact}-{locale_name}"
            if output_locale.startswith("NF-"):
                prefix = (
                    f"{self.font_config.family_name_compact}-"
                    f"{self.font_config.get_nf_variant().symbol}-{locale_name}"
                )
            return [
                directory / merged_variable_name(prefix, italic)
                for italic in (False, True)
            ]
        directory = static_output_dir(self.runtime_context.output_dir, output_locale)
        locale_name = (
            output_locale[3:] if output_locale.startswith("NF-") else output_locale
        )
        prefix = f"{self.font_config.family_name_compact}-{locale_name}"
        if output_locale.startswith("NF-"):
            prefix = (
                f"{self.font_config.family_name_compact}-"
                f"{self.font_config.get_nf_variant().symbol}-{locale_name}"
            )
        return [
            directory / f"{prefix}-{style}.ttf"
            for style in expected_static_styles(self.target_styles)
        ]

    def _cjk_stage_paths(self, output_locale: str) -> list[Path]:
        return [
            path
            for path in self._cjk_stage_expected_paths(output_locale)
            if path.is_file()
        ]

    def _build_cjk_outputs(self, process_executor: Executor) -> None:
        if self.plan.cjk_mode:
            built_any = False
            for stage, entry, output_locale in self._cjk_stage_targets():
                task_message = (
                    "Build CJK variable outputs (%s)"
                    if self.plan.cjk_mode == "variable"
                    else "Build CJK static outputs (%s)"
                )
                started_at = log_task(
                    TaskName.CJK,
                    task_message,
                    entry.display_name,
                    task_label=entry.locale_name.lower(),
                )
                if self._validate_recorded_stage(stage):
                    log_task_complete(
                        started_at,
                        f"{len(self._cjk_stage_paths(output_locale))} fonts",
                    )
                    built_any = True
                    continue

                self._invalidate_recorded_stage(stage)
                scoped_config = deepcopy(self.font_config)
                scoped_config.cjk.entries = [entry]
                output_locales = {output_locale}
                if self.plan.cjk_mode == "variable":
                    build_cjk_extended_variable_outputs(
                        scoped_config,
                        self.runtime_context,
                        process_executor,
                        output_locales,
                        started_at=started_at,
                    )
                else:
                    build_cjk_extended_static_outputs(
                        scoped_config,
                        self.runtime_context,
                        self.target_styles,
                        process_executor,
                        output_locales,
                        started_at=started_at,
                    )
                built_any = True
            self.runtime_context.is_cjk_built = built_any
        else:
            if is_ci():
                set_log_task("cjk")
                logger.debug("Skip CJK outputs because no locale is selected")
            else:
                log_task(
                    TaskName.CJK,
                    "Skip CJK outputs: reason=no CJK locale selected",
                )

    def prepare_output_root(self) -> None:
        if not self.should_use_cache:
            logger.info("Cache disabled: rebuild requested")
            shutil.rmtree(self.runtime_context.output_dir, ignore_errors=True)
            shutil.rmtree(self.runtime_context.output_woff2, ignore_errors=True)
        else:
            self._cache_matches_build()
        ensure_base_output_dirs(self.runtime_context)

    def start_build_timer(self) -> None:
        self.start_time = time.time()
        cjk_entries = self.font_config.get_selected_cjk_entries()
        cjk_summary = "off"
        if cjk_entries:
            locales = ", ".join(entry.display_name for entry in cjk_entries)
            cjk_summary = f"{self.font_config.cjk_output_format} ({locales})"
        options = [
            label
            for enabled, label in (
                (self.font_config.use_hinted, "hinting"),
                (self.font_config.enable_ligature, "ligatures"),
            )
            if enabled
        ]
        details = [
            f"  Formats: {', '.join(item.upper() for item in self.font_config.formats)}",
            f"  Styles: {', '.join(self.target_styles) if self.target_styles else 'all'}",
            f"  Options: {', '.join(options) or 'none'}",
            f"  Nerd Font: {'on' if self.font_config.nerd_font.enable else 'off'}",
            f"  CJK: {cjk_summary}",
            f"  Cache: {'on' if self.font_config.cache else 'off'}",
        ]
        if self.font_config.archive:
            details.append("  Archive: on")
        if self.font_config.width != "default":
            details.append(
                "  Width: "
                f"{self.font_config.width} "
                f"({self.font_config.glyph_width} -> "
                f"{self.font_config.get_target_width()}, "
                f"suffix {self.font_config.get_width_name()})",
            )
        if self.font_config.line_height != 1:
            details.append(f"  Line height: {self.font_config.line_height:g}")
        version = self.font_config.version_str.removeprefix("Version ")
        log_task(
            TaskName.BUILD,
            "%s %s\n%s",
            self.font_config.family_name,
            version,
            "\n".join(details),
        )

    def base_formats_to_build(
        self,
    ) -> tuple[Literal["variable", "ttf", "otf"], ...]:
        """Return only the base formats that are missing from the cache."""
        if not self.should_use_cache:
            return self.plan.required_base_formats

        missing_formats: list[Literal["variable", "ttf", "otf"]] = []
        for build_format in self.plan.required_base_formats:
            if self._has_cached_base_format(build_format):
                self._log_cache_reuse(build_format)
            else:
                missing_formats.append(build_format)
        return tuple(missing_formats)

    def _cache_matches_build(self) -> bool:
        if not self.should_use_cache or self._cache_identity_checked:
            return self._cache_identity_valid

        self._cache_identity_checked = True
        self._cache_record = read_cache_record(Path(self.runtime_context.output_root))
        if not self._cache_record:
            self._cache_identity_valid = False
            logger.info(
                "Cache miss: stage=all, reason=missing-cache-record path=%s",
                "build-cache.json",
            )
        return self._cache_identity_valid

    def _current_build_identity(self) -> dict[str, object]:
        if self._build_identity is None:
            self._build_identity = base_cache_identity(
                self.font_config,
                self.runtime_context,
            )
        return self._build_identity

    def _log_cache_reuse(
        self,
        build_format: Literal["variable", "ttf", "otf"],
    ) -> None:
        if build_format in self._cache_reuse_logged:
            return
        self._cache_reuse_logged.add(build_format)
        output_dir = {
            "variable": self.runtime_context.output_variable,
            "ttf": self.runtime_context.output_ttf,
            "otf": self.runtime_context.output_otf,
        }[build_format]
        logger.info("Reuse cached %s outputs", build_format.upper())
        logger.debug("Cached %s output path: %s", build_format, output_dir)

    def _has_cached_base_format(
        self,
        build_format: Literal["variable", "ttf", "otf"],
    ) -> bool:
        return self._validate_cached_stage(
            build_format,
            self._base_stage_expected_paths(build_format),
        )

    def _base_stage_expected_paths(self, stage: str) -> list[Path]:
        if stage == "variable":
            output_dir = Path(self.runtime_context.output_variable)
            return [
                output_dir / f"{self.font_config.family_name_compact}[wght].ttf",
                output_dir / f"{self.font_config.family_name_compact}-Italic[wght].ttf",
            ]

        if stage in {"ttf", "otf"}:
            output_dir = Path(
                self.runtime_context.output_ttf
                if stage == "ttf"
                else self.runtime_context.output_otf
            )
            return expected_static_font_paths(
                output_dir,
                self.font_config.family_name_compact,
                self.target_styles,
                f".{stage}",
            )

        if stage == "ttf-autohint":
            return expected_static_font_paths(
                self.runtime_context.output_ttf_hinted,
                self.font_config.family_name_compact,
                self.target_styles,
            )

        if stage == "woff2":
            return expected_static_font_paths(
                self.runtime_context.output_woff2,
                self.font_config.family_name_compact,
                self.target_styles,
                ".woff2",
            )

        raise ValueError(f"Unknown base stage: {stage}")

    def _validate_cached_stage(self, stage: str, paths: list[Path]) -> bool:
        if not self.should_use_cache:
            return False
        if not self._cache_matches_build():
            return False
        return validate_stage(
            Path(self.runtime_context.output_root),
            self._cache_record,
            stage,
            self._stage_cache_identity(stage),
            paths,
        )

    def _validate_recorded_stage(self, stage: str) -> bool:
        if not self.should_use_cache or not self._cache_matches_build():
            return False
        stages = (self._cache_record or {}).get("stages")
        stage_record = stages.get(stage) if isinstance(stages, dict) else None
        if not isinstance(stage_record, dict):
            logger.info("Cache miss: stage=%s, reason=missing-record", stage)
            return False
        snapshot = stage_record.get("snapshot")
        files = snapshot.get("files") if isinstance(snapshot, dict) else None
        if not isinstance(files, list) or not files:
            logger.info("Cache miss: stage=%s, reason=missing-output", stage)
            return False
        root = Path(self.runtime_context.output_root)
        cjk_stages = {
            target_stage
            for target_stage, _entry, _output_locale in self._cjk_stage_targets()
        }
        if stage not in cjk_stages:
            try:
                if not all(isinstance(relative, str) for relative in files):
                    raise ValueError("cache file list is invalid")
                paths = [root / Path(relative) for relative in sorted(files)]
                if any(
                    relative_cache_path(root, path) != relative
                    for relative, path in zip(sorted(files), paths)
                ):
                    raise ValueError("cache path is outside the output root")
            except ValueError:
                logger.info("Cache miss: stage=%s, reason=invalid-record", stage)
                return False
            return validate_stage(
                root,
                self._cache_record,
                stage,
                self._stage_cache_identity(stage),
                paths,
            )

        _entry, output_locale = self._cjk_stage_target(stage)
        paths = self._cjk_stage_expected_paths(output_locale)
        expected_files = {
            path.resolve().relative_to(root.resolve()).as_posix() for path in paths
        }
        if (
            not all(isinstance(relative, str) for relative in files)
            or set(files) != expected_files
        ):
            logger.info("Cache miss: stage=%s, reason=missing-output", stage)
            return False
        return validate_stage(
            root,
            self._cache_record,
            stage,
            self._stage_cache_identity(stage),
            paths,
        )

    def _invalidate_recorded_stage(self, stage: str) -> None:
        if not self.should_use_cache or self._cache_record is None:
            return
        stages = self._cache_record.get("stages")
        if not isinstance(stages, dict) or stage not in stages:
            return
        del stages[stage]
        persist_cache_record(
            Path(self.runtime_context.output_root),
            self._cache_record,
        )

    def _stage_cache_identity(self, stage: str) -> str:
        record = self.font_config.to_dict()
        dependencies: dict[str, str] = {}
        if stage in {"variable", "ttf", "otf"}:
            inputs: dict[str, object] = {
                "base": self._current_build_identity(),
                "target_styles": (
                    list(self.target_styles) if self.target_styles is not None else None
                ),
            }
            if stage == "variable":
                inputs["target_styles"] = None
        elif stage == "ttf-autohint":
            dependencies["ttf"] = self._stage_cache_identity("ttf")
            inputs = {
                "ttfautohint_param": self.font_config.ttfautohint_param,
                "use_hinted": self.font_config.use_hinted,
            }
        elif stage == "woff2":
            dependencies["ttf"] = self._stage_cache_identity("ttf")
            inputs = {"format": "woff2"}
        elif stage == "nf":
            upstream = "ttf-autohint" if self.font_config.use_hinted else "ttf"
            dependencies[upstream] = self._stage_cache_identity(upstream)
            inputs = {
                "nerd_font": record.get("nerd_font"),
                "width": self.font_config.width,
                "line_height": self.font_config.line_height,
            }
        elif self.plan.cjk_mode and stage in {
            target_stage for target_stage, _entry, _locale in self._cjk_stage_targets()
        }:
            entry, output_locale = self._cjk_stage_target(stage)
            upstream = "ttf-autohint" if self.font_config.use_hinted else "ttf"
            if self.plan.cjk_mode == "variable":
                upstream = "variable"
            dependencies[upstream] = self._stage_cache_identity(upstream)
            if output_locale.startswith("NF-"):
                dependencies["nf"] = self._stage_cache_identity("nf")
            inputs = {
                "entry": serialize_cjk_build_config(entry.build_config),
                "common_options": entry.common_options.to_dict(),
                "output_locale": output_locale,
                "cjk_format": self.plan.cjk_mode,
                "ttfautohint_param": self.font_config.ttfautohint_param,
            }
        else:
            inputs = {"record": record}
        return stage_identity(inputs, stage, dependencies)

    def should_build_hinted_ttf(
        self,
        base_formats: tuple[Literal["variable", "ttf", "otf"], ...],
    ) -> bool:
        if not self.font_config.needs_hinted_ttf():
            return False
        if "ttf" in base_formats:
            return True
        if not self.should_use_cache:
            return True
        if self._has_cached_hinted_ttf():
            logger.info("Reuse cached TTF-AutoHint outputs")
            logger.debug(
                "Cached TTF-AutoHint output path: %s",
                self.runtime_context.output_ttf_hinted,
            )
            return False
        return True

    def _has_cached_hinted_ttf(self) -> bool:
        return self._validate_cached_stage(
            "ttf-autohint",
            self._base_stage_expected_paths("ttf-autohint"),
        )

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
        logger.debug("Reuse cached base font outputs")

    def should_build_woff2_outputs(
        self,
        base_formats: tuple[Literal["variable", "ttf", "otf"], ...] = (),
    ) -> bool:
        if not self.font_config.wants_format("woff2") or self.font_config.debug:
            return False
        if "ttf" in base_formats or not self.should_use_cache:
            return True
        expected = self._base_stage_expected_paths("woff2")
        if not self._validate_cached_stage("woff2", expected):
            return True
        logger.info("Reuse cached WOFF2 outputs")
        logger.debug("Cached WOFF2 output path: %s", self.runtime_context.output_woff2)
        return False

    def write_build_config(self) -> None:
        record = self.font_config.to_build_record()
        record_path = Path(self.runtime_context.output_dir) / "build-config.json"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = record_path.with_name(f".{record_path.name}.tmp")
        temporary_path.write_text(
            json.dumps(record, indent=4),
            encoding="utf-8",
        )
        temporary_path.replace(record_path)

    def write_build_record(self) -> None:
        """Write the public config and the completed cache record."""
        self.write_build_config()
        self.write_cache_record()

    def write_cache_record(self) -> None:
        log_task(TaskName.BUILD, "Write cache record", force_separator=True)
        root = Path(self.runtime_context.output_root)
        stages: dict[str, dict[str, object]] = {}
        for stage in ("variable", "ttf", "otf", "ttf-autohint", "woff2"):
            files = [
                path
                for path in self._base_stage_expected_paths(stage)
                if path.is_file()
            ]
            if files:
                stages[stage] = {
                    "key": self._stage_cache_identity(stage),
                    "snapshot": output_snapshot(
                        root,
                        stage,
                        files,
                    ),
                }
        nf_dir = Path(self.runtime_context.output_nf)
        nf_files = sorted(path for path in nf_dir.rglob("*") if path.is_file())
        if nf_files:
            stages["nf"] = {
                "key": self._stage_cache_identity("nf"),
                "snapshot": output_snapshot(
                    root,
                    "nf",
                    nf_files,
                ),
            }
        if self.plan.cjk_mode:
            for stage, _entry, output_locale in self._cjk_stage_targets():
                files = self._cjk_stage_paths(output_locale)
                if not files:
                    continue
                stages[stage] = {
                    "key": self._stage_cache_identity(stage),
                    "snapshot": output_snapshot(
                        root,
                        stage,
                        files,
                    ),
                }
        record: dict[str, Any] = {
            "schema": CACHE_SCHEMA,
            "stages": stages,
        }
        persist_cache_record(root, record)
        self._cache_record = record
        self._cache_identity_checked = True
        self._cache_identity_valid = True

    def archive_outputs(self) -> None:
        started_at = log_task(TaskName.ARCHIVE, "Archive build outputs")
        archive_dir_name = "archive"
        archive_dir = join_path(self.runtime_context.output_dir, archive_dir_name)
        makedirs(archive_dir, exist_ok=True)

        archive_count = 0
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

            archive_count += 1
            logger.info(
                "Saved archive to %s",
                join_path(archive_dir, f"{zip_file_name_without_ext}.zip"),
            )
        log_task_complete(started_at, f"{archive_count} archives")

    def finish_build(self) -> None:
        freeze_str = (
            self.font_config.freeze_config_str
            if self.font_config.freeze_config_str != ""
            else "default config"
        )
        time_diff = time.time() - self.start_time
        output_root = Path(self.runtime_context.output_dir).resolve()
        cjk_locales = (
            ", ".join(
                entry.locale_name
                for entry in self.font_config.get_selected_cjk_entries()
            )
            or "none"
        )
        log_task(
            TaskName.BUILD,
            "Build completed, took %.2fs:\n"
            "  Directory: %s\n"
            "  Family: %s\n"
            "  Width: %s units\n"
            "  Feature configuration: %s\n"
            "  Nerd Font: %s\n"
            "  CJK: %s (%s)",
            time_diff,
            output_root,
            self.font_config.family_name,
            self.font_config.get_target_width(),
            freeze_str,
            "built" if self.runtime_context.is_nf_built else "not built",
            cjk_locales,
            "built" if self.runtime_context.is_cjk_built else "not built",
        )


def main(args: list[str] | None = None, version: str | None = None) -> None:
    from scripts.config.cli import parse_args

    resolved_version = version or version_tag()
    parsed_args = parse_args(args, version=resolved_version)
    use_debug_log_default = parsed_args.debug and ENVIRONMENT_VARIABLE not in environ
    if use_debug_log_default:
        environ[ENVIRONMENT_VARIABLE] = "DEBUG"
    try:
        configure_logging()
        resolver = BuildConfigResolver(version_tag=resolved_version)
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
    finally:
        if use_debug_log_default:
            del environ[ENVIRONMENT_VARIABLE]

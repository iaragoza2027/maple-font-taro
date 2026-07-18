from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fontmake.compatibility import CompatibilityChecker
from fontmake.font_project import CFFOptimization, FontProject
from fontTools.designspaceLib import DesignSpaceDocument
from glyphsLib import load, to_designspace
from ufo2ft.filters import DecomposeTransformedComponentsFilter

from scripts.font_ops.glyph_transform import smart_change_ufo_width
from scripts.font_ops.opentype import DEFAULT_COMPAT_ALIASES
from scripts.utils.files import write_json


SourceStyle = Literal["regular", "italic"]
FontmakeOutput = Literal["variable", "ttf", "otf"]


@dataclass(frozen=True, slots=True)
class PreparedGlyphsSource:
    source_path: Path
    style: SourceStyle
    designspace: DesignSpaceDocument
    errors: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class GlyphsSourceReport:
    source_path: Path
    style: SourceStyle
    errors: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class FontmakeBranchJob:
    designspace_path: Path
    output: FontmakeOutput
    target: Path
    interpolate: bool = False


class SourceCompatibilityError(RuntimeError):
    """Raised after all Glyphs source issues have been written."""


class IssueCollectingCompatibilityChecker(CompatibilityChecker):
    """Run fontmake's compatibility checks without logging every glyph."""

    def __init__(self, fonts: list[Any], default_source_idx: int):
        super().__init__(fonts, default_source_idx)
        self.glyph_issues: dict[str, set[str]] = {}

    def ensure_all_same(self, func: Any, objs: list[Any], what: str) -> bool:
        values = {func(value) for value in objs}
        if len(values) < 2:
            return True

        glyph_context = self.context[0]
        glyph_name = glyph_context.removeprefix("glyph ")
        detail = " ".join((*self.context[1:], what))
        if what == "base glyph":
            master_values = ", ".join(
                f"{font.info.styleName or 'Unknown'}={func(value)}"
                for font, value in zip(self.current_fonts, objs, strict=False)
            )
            detail = f"{detail}: {master_values}"
        self.glyph_issues.setdefault(glyph_name, set()).add(detail)
        self.okay = False
        return False


def compile_fontmake_outputs(
    prepared: PreparedGlyphsSource,
    workspace: str | Path,
    variable_output_path: str | Path,
    ttf_output_dir: str | Path,
    otf_output_dir: str | Path | None,
) -> GlyphsSourceReport:
    """Compile all requested branches from one prepared Designspace/UFO tree."""
    report = GlyphsSourceReport(
        source_path=prepared.source_path,
        style=prepared.style,
        errors=prepared.errors,
    )
    if prepared.errors:
        return report

    designspace_path = materialize_prepared_source(prepared, workspace)
    jobs = [
        FontmakeBranchJob(
            designspace_path=designspace_path,
            output="variable",
            target=Path(variable_output_path),
        ),
        FontmakeBranchJob(
            designspace_path=designspace_path,
            output="ttf",
            target=Path(ttf_output_dir),
            interpolate=True,
        ),
    ]
    if otf_output_dir is not None:
        jobs.append(
            FontmakeBranchJob(
                designspace_path=designspace_path,
                output="otf",
                target=Path(otf_output_dir),
                interpolate=True,
            )
        )

    with ThreadPoolExecutor(
        max_workers=len(jobs),
        thread_name_prefix=f"fontmake-{prepared.style}",
    ) as executor:
        list(executor.map(_compile_fontmake_branch, jobs))

    return report


def _compile_fontmake_branch(job: FontmakeBranchJob) -> None:
    project = FontProject()
    if job.output == "variable":
        job.target.parent.mkdir(parents=True, exist_ok=True)
        project.run_from_designspace(
            job.designspace_path,
            output=("variable",),
            output_path=str(job.target),
            use_production_names=False,
            remove_overlaps=False,
            autohint=False,
            subset=False,
            feature_writers=[],
            generate_GDEF=False,
            check_compatibility=True,
        )
        return

    job.target.mkdir(parents=True, exist_ok=True)
    if job.output == "otf":
        project.run_from_designspace(
            job.designspace_path,
            output=("otf",),
            output_dir=str(job.target),
            interpolate=job.interpolate,
            use_production_names=False,
            remove_overlaps=True,
            overlaps_backend="pathops",
            autohint=False,
            subset=False,
            feature_writers=[],
            filters=[DecomposeTransformedComponentsFilter()],
            generate_GDEF=False,
            check_compatibility=True,
            optimize_cff=CFFOptimization.SUBROUTINIZE,
        )
        return

    project.run_from_designspace(
        job.designspace_path,
        output=("ttf",),
        output_dir=str(job.target),
        interpolate=job.interpolate,
        use_production_names=False,
        remove_overlaps=True,
        overlaps_backend="pathops",
        autohint=False,
        subset=False,
        feature_writers=[],
        filters=[DecomposeTransformedComponentsFilter()],
        generate_GDEF=False,
        check_compatibility=True,
    )


def write_source_issue_report(
    sources: Sequence[PreparedGlyphsSource | GlyphsSourceReport],
    output_dir: str | Path,
) -> Path | None:
    """Write one deterministic source report without logging individual glyphs."""
    report_path = Path(output_dir) / "source-issues.json"
    error_count = sum(len(source.errors) for source in sources)
    if error_count == 0:
        report_path.unlink(missing_ok=True)
        return None

    report_path.parent.mkdir(parents=True, exist_ok=True)
    ordered_sources = sorted(
        sources,
        key=lambda source: 0 if source.style == "regular" else 1,
    )
    write_json(
        report_path,
        {
            source.style: {
                "source": source.source_path.as_posix(),
                "reused_regular_master_layers": [],
                "errors": list(source.errors),
            }
            for source in ordered_sources
        },
    )
    print(f"Source compatibility report: {report_path} ({error_count} errors)")
    return report_path


def validate_source_reports(
    sources: Sequence[PreparedGlyphsSource | GlyphsSourceReport],
    output_dir: str | Path,
) -> None:
    """Write combined source issues and fail after every source was checked."""
    report_path = write_source_issue_report(sources, output_dir)
    if any(source.errors for source in sources):
        raise SourceCompatibilityError(
            f"Glyphs source compatibility failed; see {report_path}"
        )


def prepare_glyphs_source(
    source_path: str | Path,
    style: SourceStyle,
    target_width: int | None = None,
    original_ref_width: int = 600,
) -> PreparedGlyphsSource:
    """Load and normalize one Glyphs source for every fontmake output branch."""
    path = Path(source_path)
    with path.open(encoding="utf-8") as source_file:
        glyphs_font = load(source_file)
    glyphs_font.classes = []
    glyphs_font.featurePrefixes = []
    glyphs_font.features = []
    designspace = to_designspace(
        glyphs_font,
        generate_GDEF=False,
        minimal=True,
        store_editor_state=False,
        write_skipexportglyphs=True,
    )

    weight_axis = next((axis for axis in designspace.axes if axis.tag == "wght"), None)
    if weight_axis is None:
        raise ValueError(f"Glyphs source is missing a wght axis: {path}")
    weight_axis.default = 400

    sources = list(designspace.sources)
    default_source = next(
        (source for source in sources if source.location.get("Weight") == 400),
        None,
    )
    if default_source is None or default_source.font is None:
        raise ValueError(f"Glyphs source is missing a wght 400 master: {path}")

    for source in sources:
        is_default = source is default_source
        source.copyLib = is_default
        source.copyGroups = is_default
        source.copyFeatures = is_default
        source.copyInfo = is_default
        if source.font is None:
            raise ValueError(f"Glyphs source master has no UFO font: {path}")
        source.font.features.text = ""

    skip_export = set(designspace.lib.get("public.skipExportGlyphs", ()))
    glyph_names = sorted(
        set().union(
            *(set(source.font.keys()) for source in sources if source.font is not None)
        )
        - skip_export
    )
    errors: list[dict[str, Any]] = []
    default_font = default_source.font
    for glyph_name in glyph_names:
        available_sources = [
            source
            for source in sources
            if source.font is not None and glyph_name in source.font
        ]
        missing_sources = [
            source
            for source in sources
            if source.font is not None and glyph_name not in source.font
        ]
        if not missing_sources:
            continue
        if glyph_name not in default_font:
            errors.append(
                {
                    "glyph": glyph_name,
                    "kind": "missing_regular_master_layer",
                    "available_masters": [
                        source.styleName or source.name or "Unknown"
                        for source in available_sources
                    ],
                    "missing_masters": [
                        source.styleName or source.name or "Unknown"
                        for source in missing_sources
                    ],
                }
            )
            continue
        default_glyph = default_font[glyph_name]
        for source in missing_sources:
            assert source.font is not None
            source.font.addGlyph(default_glyph.copy())

    for source in sources:
        assert source.font is not None
        _alias_ufo_codepoints(source.font)
        if target_width is not None:
            smart_change_ufo_width(
                source.font,
                target_width=target_width,
                original_ref_width=original_ref_width,
            )

    source_fonts = [source.font for source in sources]
    checker = IssueCollectingCompatibilityChecker(
        source_fonts,
        sources.index(default_source),
    )
    checker.check()
    errors.extend(
        {
            "glyph": glyph_name,
            "kind": "incompatible_masters",
            "details": sorted(details),
        }
        for glyph_name, details in sorted(checker.glyph_issues.items())
    )
    errors.sort(key=lambda item: (item["glyph"], item["kind"]))

    return PreparedGlyphsSource(
        source_path=path,
        style=style,
        designspace=designspace,
        errors=tuple(errors),
    )


def materialize_prepared_source(
    prepared: PreparedGlyphsSource,
    workspace: str | Path,
) -> Path:
    """Write one immutable Designspace/UFO tree for all fontmake branches."""
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True)
    designspace_path = root / f"{prepared.style}.designspace"
    prepared.designspace.path = str(designspace_path)

    for index, source in enumerate(prepared.designspace.sources):
        if source.font is None:
            raise ValueError(f"Prepared source has no UFO font: {source.name}")
        filename = Path(source.filename or f"master-{index}.ufo").name
        ufo_path = root / filename
        source.font.save(ufo_path, overwrite=True)
        source.font = None
        source.path = str(ufo_path.resolve())

    prepared.designspace.write(designspace_path)
    return designspace_path


def _alias_ufo_codepoints(font: Any) -> None:
    unicode_glyphs = {
        codepoint: glyph for glyph in font for codepoint in glyph.unicodes
    }
    for alias, source in DEFAULT_COMPAT_ALIASES.items():
        glyph = unicode_glyphs.get(source)
        if glyph is not None and alias not in glyph.unicodes:
            glyph.unicodes.append(alias)

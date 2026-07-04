from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Literal

from fontTools.subset import parse_unicodes
from fontTools.ttLib import TTFont

from source.py.cjk.vf import load_font_eager, weight_axis


OutlineMode = Literal["auto", "glyf", "cff2"]
UnicodePreset = Literal["cn", "jp", "tc", "kr"]
CJK_MASTER_WEIGHTS = (100, 400, 800)
CJKMasterLocations = dict[int, dict[str, float]]


DEFAULT_MAPLE_HHEA_METRICS: dict[str, int] = {
    "ascent": 990,
    "descent": -270,
    "lineGap": 0,
    "caretSlopeRise": 1,
    "caretSlopeRun": 0,
    "caretOffset": 0,
}

DEFAULT_MAPLE_OS2_METRICS: dict[str, int] = {
    "sTypoAscender": 990,
    "sTypoDescender": -270,
    "sTypoLineGap": 0,
    "usWinAscent": 1020,
    "usWinDescent": 300,
    "sxHeight": 550,
    "sCapHeight": 730,
    "usWidthClass": 5,
    "fsSelection": 64,
}

DEFAULT_MAPLE_POST_METRICS: dict[str, int] = {
    "isFixedPitch": 1,
    "underlinePosition": -125,
    "underlineThickness": 50,
    "italicAngle": 0,
}

DEFAULT_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x2460, 0x24FF),
    (0x2E80, 0x2EFF),
    (0x2F00, 0x2FDF),
    (0x2FF0, 0x2FFF),
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x3100, 0x312F),
    (0x31A0, 0x31EF),
    (0x3200, 0x33FF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F),
    (0xFF00, 0xFFEF),
)

DEFAULT_CN_RANGES = DEFAULT_CJK_RANGES

DEFAULT_JP_RANGES: tuple[tuple[int, int], ...] = (
    (0x2460, 0x24FF),
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x31F0, 0x31FF),
    (0x3200, 0x33FF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F),
    (0xFF00, 0xFFEF),
)

DEFAULT_TC_RANGES: tuple[tuple[int, int], ...] = (
    (0x2460, 0x24FF),
    (0x2E80, 0x2EFF),
    (0x2F00, 0x2FDF),
    (0x2FF0, 0x2FFF),
    (0x3000, 0x303F),
    (0x3100, 0x312F),
    (0x31A0, 0x31EF),
    (0x3200, 0x33FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F),
    (0xFF00, 0xFFEF),
)

DEFAULT_KR_RANGES: tuple[tuple[int, int], ...] = (
    (0x2460, 0x24FF),
    (0x3000, 0x303F),
    (0x3130, 0x318F),
    (0x3200, 0x33FF),
    (0x4E00, 0x9FFF),
    (0xA960, 0xA97F),
    (0xAC00, 0xD7AF),
    (0xD7B0, 0xD7FF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F),
    (0xFF00, 0xFFEF),
)


@dataclass(frozen=True)
class CJKWeightInstance:
    """Named weight instance copied from the feature font."""

    name: str
    coordinate: float


def ordered_master_locations(
    masters: CJKMasterLocations,
) -> tuple[
    tuple[int, dict[str, float]],
    tuple[int, dict[str, float]],
    tuple[int, dict[str, float]],
]:
    """Return CJK master locations in output weight order."""
    missing = [weight for weight in CJK_MASTER_WEIGHTS if weight not in masters]
    if missing:
        raise ValueError(f"source.masters is missing output weights: {missing}")
    return tuple((weight, masters[weight]) for weight in CJK_MASTER_WEIGHTS)  # type: ignore[return-value]


@dataclass(frozen=True)
class CJKSourceConfig:
    """Input CJK variable font configuration."""

    path: Path
    masters: CJKMasterLocations
    outline_mode: OutlineMode = "auto"
    drop_tables: tuple[str, ...] = ()


@dataclass(frozen=True)
class CJKUnicodeConfig:
    """Unicode filtering configuration for the source font."""

    ranges: tuple[tuple[int, int], ...] = DEFAULT_CJK_RANGES
    filter_encoding: str | None = None
    exclude_feature_codepoints: bool = True


UNICODE_PRESETS: dict[UnicodePreset, CJKUnicodeConfig] = {
    "cn": CJKUnicodeConfig(ranges=DEFAULT_CN_RANGES),
    "jp": CJKUnicodeConfig(ranges=DEFAULT_JP_RANGES, filter_encoding="cp932"),
    "tc": CJKUnicodeConfig(ranges=DEFAULT_TC_RANGES),
    "kr": CJKUnicodeConfig(ranges=DEFAULT_KR_RANGES),
}


@dataclass(frozen=True)
class CJKTransformConfig:
    """Width and outline normalization applied to added CJK glyphs."""

    target_advance_width: int = 1200
    x_scale: float = 1
    y_scale: float = 1
    x_shift: int = 0
    y_shift: int = 0
    italic_angle: float = 10


@dataclass(frozen=True)
class CJKOutputConfig:
    """Output file layout."""

    dir: Path = Path("source/cjk")
    regular_variable: str = "MapleMono-CJK-VF.ttf"
    italic_variable: str = "MapleMono-CJK-Italic-VF.ttf"
    static_dir: str = "static"
    static_hash: str = "static.sha256"
    archive_name: str = "cjk-base-static.zip"


@dataclass(frozen=True)
class CJKNamingConfig:
    """Font family and file naming configuration."""

    family_name: str = "Maple Mono CJK"
    postscript_prefix: str = "MapleMonoCJK"
    static_file_prefix: str = "MapleMonoCJK"


@dataclass(frozen=True)
class CJKBuildConfig:
    """Complete CJK build configuration."""

    source: CJKSourceConfig
    feature_font_path: Path = Path("source/MapleMono-CN-feature-VF.ttf")
    output: CJKOutputConfig = field(default_factory=CJKOutputConfig)
    naming: CJKNamingConfig = field(default_factory=CJKNamingConfig)
    unicode: CJKUnicodeConfig = field(default_factory=CJKUnicodeConfig)
    transform: CJKTransformConfig = field(default_factory=CJKTransformConfig)
    temp_dir: Path = Path("source/cjk/temp")
    hhea_metrics: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_MAPLE_HHEA_METRICS)
    )
    os2_metrics: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_MAPLE_OS2_METRICS)
    )
    post_metrics: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_MAPLE_POST_METRICS)
    )
    allow_incompatible_glyphs: bool = False


def parse_codepoint(value: str | int) -> int:
    """Parse decimal or hex codepoint values."""
    if isinstance(value, int):
        return value
    return int(value, 16 if value.lower().startswith("0x") else 10)


def ranges_from_codepoints(codepoints: Iterable[int]) -> tuple[tuple[int, int], ...]:
    """Compress codepoints into stable contiguous ranges."""
    ordered = sorted(set(codepoints))
    if not ordered:
        return ()

    ranges: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for codepoint in ordered[1:]:
        if codepoint == previous + 1:
            previous = codepoint
            continue
        ranges.append((start, previous))
        start = previous = codepoint
    ranges.append((start, previous))
    return tuple(ranges)


def parse_range(value: str | list[Any] | tuple[Any, Any]) -> tuple[int, int]:
    """Parse a JSON Unicode range entry."""
    if isinstance(value, str):
        if not value.lower().startswith("0x") and "0x" not in value.lower():
            parsed = parse_unicodes(value)
            ranges = ranges_from_codepoints(parsed)
            if len(ranges) == 1:
                return ranges[0]
            raise ValueError(
                "JSON range entries must describe one range each; "
                f"use a list for multiple ranges: {value!r}"
            )
        delimiter = ".." if ".." in value else "-"
        if delimiter not in value:
            point = parse_codepoint(value)
            return point, point
        start, end = value.split(delimiter, 1)
        return parse_codepoint(start), parse_codepoint(end)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return parse_codepoint(value[0]), parse_codepoint(value[1])
    raise ValueError(f"Invalid Unicode range: {value!r}")


def validate_ranges(ranges: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """Validate parsed Unicode ranges."""
    result = tuple(ranges)
    for start, end in result:
        if start > end:
            raise ValueError(f"Invalid Unicode range order: {start:#x}-{end:#x}")
        if start < 0 or end > 0x10FFFF:
            raise ValueError(f"Unicode range out of bounds: {start:#x}-{end:#x}")
    return result


def parse_master_locations(value: Any) -> CJKMasterLocations:
    """Parse output-weight keyed source master locations from JSON."""
    if not isinstance(value, dict):
        raise ValueError(
            "source.masters must be an object keyed by output weights 100, 400, and 800"
        )
    masters: CJKMasterLocations = {}
    for raw_weight, raw_axes in value.items():
        try:
            output_weight = int(raw_weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid source master output weight: {raw_weight}"
            ) from exc
        if output_weight not in CJK_MASTER_WEIGHTS:
            raise ValueError(
                "source.masters keys must be exactly output weights 100, 400, and 800"
            )
        if not isinstance(raw_axes, dict):
            raise ValueError(f"source.masters.{output_weight} must be an object")
        axes = {str(axis): float(coordinate) for axis, coordinate in raw_axes.items()}
        if "wght" not in axes:
            raise ValueError(f"source.masters.{output_weight} must include wght")
        masters[output_weight] = axes
    ordered_master_locations(masters)
    return masters


def unicode_config_from_spec(
    spec: str,
    exclude_feature_codepoints: bool = True,
) -> CJKUnicodeConfig:
    """Resolve a named Unicode preset or pyftsubset-style unicode range."""
    if spec in UNICODE_PRESETS:
        return replace(
            UNICODE_PRESETS[spec],
            exclude_feature_codepoints=exclude_feature_codepoints,
        )

    ranges = validate_ranges(ranges_from_codepoints(parse_unicodes(spec)))
    if not ranges:
        raise ValueError(f"No Unicode codepoints parsed from: {spec}")
    return CJKUnicodeConfig(
        ranges=ranges,
        exclude_feature_codepoints=exclude_feature_codepoints,
    )


def apply_unicode_override(
    config: CJKBuildConfig,
    unicode_spec: str | None,
) -> CJKBuildConfig:
    """Override a build config's Unicode filter from CLI input."""
    if not unicode_spec:
        return config
    unicode_config = unicode_config_from_spec(
        unicode_spec,
        exclude_feature_codepoints=config.unicode.exclude_feature_codepoints,
    )
    return replace(config, unicode=unicode_config)


def parse_axis_assignment(value: str) -> tuple[str, float]:
    """Parse a CLI axis assignment like ROND=100."""
    if "=" not in value:
        raise ValueError(f"Axis assignment must use TAG=VALUE syntax: {value}")
    axis, raw_value = value.split("=", 1)
    axis = axis.strip()
    if not axis:
        raise ValueError(f"Axis tag is empty: {value}")
    return axis, float(raw_value)


def parse_axis_assignments(values: Iterable[str] | None) -> dict[str, float]:
    """Parse CLI axis assignments into a dictionary."""
    axes: dict[str, float] = {}
    for value in values or ():
        axis, coordinate = parse_axis_assignment(value)
        axes[axis] = coordinate
    return axes


def detect_outline_mode(
    font: TTFont, requested: OutlineMode
) -> Literal["glyf", "cff2"]:
    """Resolve an outline mode from config and font tables."""
    if requested == "glyf":
        if "glyf" not in font:
            raise ValueError(
                "Requested glyf outlines, but source font has no glyf table"
            )
        return "glyf"
    if requested == "cff2":
        if "CFF2" not in font:
            raise ValueError(
                "Requested CFF2 outlines, but source font has no CFF2 table"
            )
        return "cff2"
    if "glyf" in font:
        return "glyf"
    if "CFF2" in font:
        return "cff2"
    if "CFF " in font:
        raise ValueError(
            "CFF source fonts are static-only; this CJK builder requires a glyf or CFF2 variable font"
        )
    raise ValueError("Source font must contain either glyf or CFF2 outlines")


def infer_weight_values(
    source_path: Path,
    wght_min: float | None = None,
    wght_regular: float | None = None,
    wght_max: float | None = None,
) -> tuple[float, float, float]:
    """Infer missing weight coordinates from a source variable font."""
    font = load_font_eager(source_path)
    try:
        if "fvar" not in font:
            raise ValueError(f"Source font must be variable: {source_path}")
        axis = weight_axis(font)
        if axis is None:
            raise ValueError(f"Source font is missing wght axis: {source_path}")
        return (
            float(axis.minValue if wght_min is None else wght_min),
            float(axis.defaultValue if wght_regular is None else wght_regular),
            float(axis.maxValue if wght_max is None else wght_max),
        )
    finally:
        font.close()


def build_master_locations(
    source_path: Path,
    fixed_axes: dict[str, float],
    wght_min: float | None = None,
    wght_regular: float | None = None,
    wght_max: float | None = None,
) -> CJKMasterLocations:
    """Build output-weight keyed master locations from source axis coordinates."""
    min_weight, regular_weight, max_weight = infer_weight_values(
        source_path,
        wght_min,
        wght_regular,
        wght_max,
    )
    if not min_weight <= regular_weight <= max_weight:
        raise ValueError("wght values must be ordered min <= regular <= max")

    return {
        100: {**fixed_axes, "wght": min_weight},
        400: {**fixed_axes, "wght": regular_weight},
        800: {**fixed_axes, "wght": max_weight},
    }


def resolve_cli_path(value: str | None) -> Path | None:
    """Resolve an optional CLI path relative to the current working directory."""
    return Path(value).expanduser() if value else None


def resolve_output_config(
    base: CJKOutputConfig,
    output_dir: str | None = None,
    regular_output: str | None = None,
    italic_output: str | None = None,
    static_dir: str | None = None,
    static_hash: str | None = None,
    archive_name: str | None = None,
) -> CJKOutputConfig:
    """Resolve CLI output overrides into the shared output directory model."""
    directory = Path(output_dir).expanduser() if output_dir else base.dir
    regular_name = base.regular_variable
    italic_name = base.italic_variable

    for raw_output, attr in (
        (regular_output, "regular"),
        (italic_output, "italic"),
    ):
        if not raw_output:
            continue
        output_path = Path(raw_output).expanduser()
        if output_path.parent != Path("."):
            if output_dir and output_path.parent != directory:
                raise ValueError(
                    f"{attr} output parent conflicts with --output-dir: {output_path}"
                )
            directory = output_path.parent
        if attr == "regular":
            regular_name = output_path.name
        else:
            italic_name = output_path.name

    return CJKOutputConfig(
        dir=directory,
        regular_variable=regular_name,
        italic_variable=italic_name,
        static_dir=static_dir or base.static_dir,
        static_hash=static_hash or base.static_hash,
        archive_name=archive_name or base.archive_name,
    )


def default_output_config() -> CJKOutputConfig:
    """Choose default output names for generated TTF variable fonts."""
    return CJKOutputConfig(
        regular_variable="MapleMono-CJK-VF.ttf",
        italic_variable="MapleMono-CJK-Italic-VF.ttf",
    )


def apply_cli_overrides(
    config: CJKBuildConfig, args: argparse.Namespace
) -> CJKBuildConfig:
    """Apply direct CLI overrides on top of a JSON or default config."""
    source_path = resolve_cli_path(getattr(args, "source", None)) or config.source.path
    fixed_axes = parse_axis_assignments(getattr(args, "axis", None))
    has_master_override = fixed_axes or any(
        getattr(args, name, None) is not None
        for name in ("wght_min", "wght_regular", "wght_max")
    )
    masters = (
        build_master_locations(
            source_path,
            fixed_axes,
            getattr(args, "wght_min", None),
            getattr(args, "wght_regular", None),
            getattr(args, "wght_max", None),
        )
        if has_master_override
        else config.source.masters
    )
    source = CJKSourceConfig(
        path=source_path,
        masters=masters,
        outline_mode=getattr(args, "outline_mode", None) or config.source.outline_mode,
        drop_tables=tuple(
            getattr(args, "drop_table", None) or config.source.drop_tables
        ),
    )

    output = resolve_output_config(
        config.output,
        getattr(args, "output_dir", None),
        getattr(args, "regular_output", None),
        getattr(args, "italic_output", None),
        getattr(args, "static_dir", None),
        getattr(args, "static_hash", None),
        getattr(args, "archive_name", None),
    )
    naming = CJKNamingConfig(
        family_name=getattr(args, "family_name", None) or config.naming.family_name,
        postscript_prefix=getattr(args, "postscript_prefix", None)
        or config.naming.postscript_prefix,
        static_file_prefix=getattr(args, "static_file_prefix", None)
        or config.naming.static_file_prefix,
    )
    unicode = config.unicode
    if getattr(args, "filter_encoding", None) is not None:
        unicode = replace(unicode, filter_encoding=args.filter_encoding)
    if getattr(args, "include_feature_codepoints", False):
        unicode = replace(unicode, exclude_feature_codepoints=False)

    transform = CJKTransformConfig(
        target_advance_width=getattr(args, "target_advance_width", None)
        or config.transform.target_advance_width,
        x_scale=getattr(args, "x_scale", None) or config.transform.x_scale,
        y_scale=getattr(args, "y_scale", None) or config.transform.y_scale,
        x_shift=getattr(args, "x_shift", None)
        if getattr(args, "x_shift", None) is not None
        else config.transform.x_shift,  # type: ignore
        y_shift=getattr(args, "y_shift", None)
        if getattr(args, "y_shift", None) is not None
        else config.transform.y_shift,  # type: ignore
        italic_angle=getattr(args, "italic_angle", None)
        or config.transform.italic_angle,
    )

    return replace(
        config,
        source=source,
        feature_font_path=resolve_cli_path(getattr(args, "feature_font", None))
        or config.feature_font_path,
        output=output,
        naming=naming,
        unicode=unicode,
        transform=transform,
        temp_dir=resolve_cli_path(getattr(args, "temp_dir", None)) or config.temp_dir,
        allow_incompatible_glyphs=getattr(args, "allow_incompatible_glyphs", False)
        or config.allow_incompatible_glyphs,
    )


def config_from_cli(args: argparse.Namespace) -> CJKBuildConfig:
    """Build a CJK config from direct CLI flags."""
    source_path = resolve_cli_path(getattr(args, "source", None))
    if source_path is None:
        raise ValueError("--source is required when --config is not provided")
    outline_mode = getattr(args, "outline_mode", None) or "auto"
    output = default_output_config()
    config = CJKBuildConfig(
        source=CJKSourceConfig(
            path=source_path,
            masters=build_master_locations(
                source_path,
                parse_axis_assignments(getattr(args, "axis", None)),
                getattr(args, "wght_min", None),
                getattr(args, "wght_regular", None),
                getattr(args, "wght_max", None),
            ),
            outline_mode=outline_mode,
            drop_tables=tuple(getattr(args, "drop_table", None) or ()),
        ),
        feature_font_path=resolve_cli_path(getattr(args, "feature_font", None))
        or Path("source/MapleMono-CN-feature-VF.ttf"),
        output=output,
    )
    return apply_cli_overrides(config, args)


def config_from_json(config_path: str | Path) -> CJKBuildConfig:
    """Load a CJK build config from JSON."""
    path = Path(config_path)
    data = json.loads(path.read_text())
    base_dir = path.parent

    def resolve_config_path(value: str | None, default: str) -> Path:
        raw = Path(value or default)
        if raw.is_absolute():
            return raw
        repo_relative = Path.cwd() / raw
        if repo_relative.exists() or str(raw).startswith("source/"):
            return repo_relative
        return base_dir / raw

    source_data = data.get("source", {})
    if not source_data.get("path"):
        raise ValueError("source.path is required")
    outline_mode = source_data.get("outline_mode", "auto")
    if outline_mode not in {"auto", "glyf", "cff2"}:
        raise ValueError("source.outline_mode must be one of: auto, glyf, cff2")

    unicode_data = data.get("unicode", {})
    transform_data = data.get("transform", {})
    output_data = data.get("output", {})
    naming_data = data.get("naming", {})

    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=resolve_config_path(source_data.get("path"), ""),
            masters=parse_master_locations(source_data.get("masters")),
            outline_mode=outline_mode,
            drop_tables=tuple(source_data.get("drop_tables", ())),
        ),
        feature_font_path=resolve_config_path(
            data.get("feature_font"), "source/MapleMono-CN-feature-VF.ttf"
        ),
        output=CJKOutputConfig(
            dir=resolve_config_path(output_data.get("dir"), "source/cjk"),
            regular_variable=output_data.get(
                "regular_variable", "MapleMono-CJK-VF.ttf"
            ),
            italic_variable=output_data.get(
                "italic_variable", "MapleMono-CJK-Italic-VF.ttf"
            ),
            static_dir=output_data.get("static_dir", "static"),
            static_hash=output_data.get("static_hash", "static.sha256"),
            archive_name=output_data.get("archive_name", "cjk-base-static.zip"),
        ),
        naming=CJKNamingConfig(
            family_name=naming_data.get("family_name", "Maple Mono CJK"),
            postscript_prefix=naming_data.get("postscript_prefix", "MapleMonoCJK"),
            static_file_prefix=naming_data.get("static_file_prefix", "MapleMonoCJK"),
        ),
        unicode=CJKUnicodeConfig(
            ranges=validate_ranges(
                parse_range(item) for item in unicode_data.get("ranges", [])
            )
            or DEFAULT_CJK_RANGES,
            filter_encoding=unicode_data.get("filter_encoding"),
            exclude_feature_codepoints=unicode_data.get(
                "exclude_feature_codepoints", True
            ),
        ),
        transform=CJKTransformConfig(
            target_advance_width=int(transform_data.get("target_advance_width", 1200)),
            x_scale=float(transform_data.get("x_scale", 1)),
            y_scale=float(transform_data.get("y_scale", 1)),
            x_shift=int(transform_data.get("x_shift", 0)),
            y_shift=int(transform_data.get("y_shift", 0)),
            italic_angle=float(transform_data.get("italic_angle", 10)),
        ),
        temp_dir=resolve_config_path(data.get("temp_dir"), "source/cjk/temp"),
        allow_incompatible_glyphs=bool(data.get("allow_incompatible_glyphs", False)),
    )


def add_cjk_arguments(parser: argparse.ArgumentParser) -> None:
    """Add custom CJK build arguments to an argparse parser."""
    parser.add_argument(
        "--config",
        type=str,
        help="Path to a CJK build JSON config",
    )
    parser.add_argument("--source", help="Source glyf/CFF2 variable font path")
    parser.add_argument(
        "--feature-font",
        help="Feature variable font used as the source of weight/name metadata",
    )
    parser.add_argument(
        "--outline-mode",
        choices=("auto", "glyf", "cff2"),
        help="Expected source outline format",
    )
    parser.add_argument(
        "--axis",
        action="append",
        help="Fixed source axis coordinate, for example ROND=100",
    )
    parser.add_argument("--wght-min", type=float, help="Source minimum wght coordinate")
    parser.add_argument(
        "--wght-regular",
        type=float,
        help="Source regular/default wght coordinate",
    )
    parser.add_argument("--wght-max", type=float, help="Source maximum wght coordinate")
    parser.add_argument(
        "--drop-table",
        action="append",
        help="Source table tag to drop before subsetting; repeat as needed",
    )
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument(
        "--regular-output", help="Regular variable output file name/path"
    )
    parser.add_argument("--italic-output", help="Italic variable output file name/path")
    parser.add_argument("--static-dir", help="Static font output subdirectory")
    parser.add_argument("--static-hash", help="Static hash file name")
    parser.add_argument("--archive-name", help="Static archive file name")
    parser.add_argument("--family-name", help="Output family name")
    parser.add_argument("--postscript-prefix", help="Output PostScript name prefix")
    parser.add_argument("--static-file-prefix", help="Static font file prefix")
    parser.add_argument("--filter-encoding", help="Optional Unicode encoding filter")
    parser.add_argument(
        "--include-feature-codepoints",
        action="store_true",
        help="Do not exclude codepoints already covered by the feature font",
    )
    parser.add_argument(
        "--unicodes",
        help=(
            "Unicode preset (cn, jp, tc, kr) or pyftsubset-style range, "
            "for example 4E00-9FFF,3000-303F"
        ),
    )
    parser.add_argument("--target-advance-width", type=int, help="Target CJK width")
    parser.add_argument("--x-scale", type=float, help="CJK glyph X scale")
    parser.add_argument("--y-scale", type=float, help="CJK glyph Y scale")
    parser.add_argument("--x-shift", type=int, help="CJK glyph X shift")
    parser.add_argument("--y-shift", type=int, help="CJK glyph Y shift")
    parser.add_argument("--italic-angle", type=float, help="Generated italic angle")
    parser.add_argument("--temp-dir", help="Temporary build directory")
    parser.add_argument(
        "--allow-incompatible-glyphs",
        action="store_true",
        help="Keep incompatible glyf glyphs fixed instead of failing",
    )
    parser.add_argument(
        "--vf-only",
        action="store_true",
        help="only rebuild variable fonts and skip static font generation",
    )

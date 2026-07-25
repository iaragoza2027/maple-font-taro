from __future__ import annotations

import hashlib
from os import listdir, makedirs, remove
from pathlib import Path
import shutil
from typing import Any

from scripts.config.base import ResolvedConfig
from scripts.config.runtime import BuildRuntimeContext
from fontTools.designspaceLib import DesignSpaceDocument
from scripts.font_ops.constant import DEFAULT_NAMING_MAPPING
from scripts.font_ops.fonttools import TTFont
from scripts.utils.files import join_path


FONT_ARTIFACT_SUFFIXES = {".otf", ".ttf", ".woff", ".woff2", ".zip"}
IGNORED_OUTPUT_DIRS = {".cjk-temp", "temp"}


def is_target_style_file(file_name: str, target_styles: list[str] | None) -> bool:
    if target_styles is None:
        return True
    stem = file_name
    for suffix in (".woff2", ".ttf", ".otf"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem.rsplit("-", 1)[-1] in target_styles


def expected_static_styles(target_styles: list[str] | None) -> tuple[str, ...]:
    if target_styles is not None:
        return tuple(target_styles)
    return tuple(DEFAULT_NAMING_MAPPING)


def expected_static_font_paths(
    output_dir: str | Path,
    family_name_compact: str,
    target_styles: list[str] | None,
    extension: str = ".ttf",
) -> list[Path]:
    """Return the exact static artifacts owned by the current build."""
    directory = Path(output_dir)
    return [
        directory
        / (
            f"{family_name_compact}-{style}.ttf.woff2"
            if extension == ".woff2"
            else f"{family_name_compact}-{style}{extension}"
        )
        for style in expected_static_styles(target_styles)
    ]


def require_existing_files(paths: list[Path], stage: str) -> None:
    """Fail before scheduling a stage when an explicit input is unavailable."""
    missing = [path for path in paths if not path.is_file()]
    if missing:
        formatted = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing {stage} input files: {formatted}")


def require_unique_targets(paths: list[Path], stage: str) -> None:
    """Reject output collisions before parallel work can overwrite a result."""
    seen: set[Path] = set()
    duplicates: list[Path] = []
    for path in paths:
        if path in seen and path not in duplicates:
            duplicates.append(path)
        seen.add(path)
    if duplicates:
        formatted = ", ".join(str(path) for path in duplicates)
        raise ValueError(f"Duplicate {stage} output paths: {formatted}")


def is_valid_font_file(font_path: Path) -> bool:
    if not font_path.is_file() or font_path.stat().st_size == 0:
        return False
    try:
        font = TTFont(font_path, lazy=True)
        font.close()
    except Exception:
        return False
    return True


def has_cached_style_outputs(
    output_dir: str | Path,
    extension: str,
    target_styles: list[str] | None,
    family_name_compact: str,
) -> bool:
    directory = Path(output_dir)
    if not directory.is_dir():
        return False
    expected_files = expected_static_font_paths(
        directory,
        family_name_compact,
        target_styles,
        extension,
    )
    return all(is_valid_font_file(font_path) for font_path in expected_files)


def _hash_file(hasher: Any, path: Path, relative_to: Path) -> None:
    hasher.update(path.relative_to(relative_to).as_posix().encode("utf-8"))
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)


def _dimensions_identity(source_dir: Path) -> dict[str, object]:
    identity: dict[str, object] = {}
    for path in sorted(source_dir.glob("*.designspace")):
        document = DesignSpaceDocument.fromfile(path)
        dimensions = document.lib.get("GSDimensionPlugin.Dimensions")
        if not isinstance(dimensions, dict) or not dimensions:
            raise ValueError(
                "Designspace is missing GSDimensionPlugin.Dimensions: "
                f"{path}. Run `uv run task.py designspace`."
            )
        identity[path.name] = dimensions
    if set(identity) != {
        "MapleMono[wght].designspace",
        "MapleMono-Italic[wght].designspace",
    }:
        raise ValueError(
            "Expected regular and italic Maple Mono designspaces with "
            "GSDimensionPlugin.Dimensions"
        )
    return identity


def _feature_fingerprint(source_dir: Path) -> str:
    root = Path(source_dir)
    paths = sorted((root / "features").glob("*.fea"))

    hasher = hashlib.sha256()
    for path in paths:
        _hash_file(hasher, path, root)
    return hasher.hexdigest()


def base_cache_identity(
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
) -> dict[str, Any]:
    record = font_config.to_dict()
    record.pop("nerd_font", None)
    record.pop("cjk", None)
    behavior = record.get("behavior")
    if isinstance(behavior, dict):
        for key in ("formats", "archive", "cache", "cjk_output_format", "use_cjk_both"):
            behavior.pop(key, None)
    metrics = record.get("metrics")
    if isinstance(metrics, dict):
        for key in ("pool_size", "github_mirror"):
            metrics.pop(key, None)
    return {
        "schema": 3,
        "config": record,
        "sources": _dimensions_identity(Path(runtime_context.src_dir)),
        "features": _feature_fingerprint(Path(runtime_context.src_dir)),
    }


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


def cleanup_unselected_base_formats(
    font_config: ResolvedConfig,
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

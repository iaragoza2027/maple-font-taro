from __future__ import annotations

import hashlib
from os import listdir, makedirs, remove
from pathlib import Path
import shutil
from typing import Any

from scripts.config.base import ResolvedConfig
from scripts.config.runtime import BuildRuntimeContext
from scripts.font_ops.constant import DEFAULT_NAMING_MAPPING
from scripts.font_ops.fonttools import TTFont
from scripts.utils.files import join_path


FONT_ARTIFACT_SUFFIXES = {".otf", ".ttf", ".woff", ".woff2", ".zip"}
IGNORED_OUTPUT_DIRS = {".cjk-temp", "temp"}


def summarize_output_artifacts(output_root: str | Path) -> list[tuple[str, int]]:
    """Count published font and archive artifacts by top-level output directory."""
    root = Path(output_root)
    if not root.is_dir():
        return []

    summary: list[tuple[str, int]] = []
    directories = (path for path in root.iterdir() if path.is_dir())
    for directory in sorted(directories, key=lambda path: path.name):
        if directory.name in IGNORED_OUTPUT_DIRS:
            continue
        count = sum(
            1
            for artifact in directory.rglob("*")
            if artifact.is_file() and artifact.suffix.lower() in FONT_ARTIFACT_SUFFIXES
        )
        if count:
            summary.append((directory.name, count))
    return summary


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
    expected_files = {
        directory
        / (
            f"{family_name_compact}-{style}.ttf.woff2"
            if extension == ".woff2"
            else f"{family_name_compact}-{style}{extension}"
        )
        for style in expected_static_styles(target_styles)
    }
    return all(is_valid_font_file(font_path) for font_path in expected_files)


def _hash_file(hasher: Any, path: Path, relative_to: Path) -> None:
    hasher.update(path.relative_to(relative_to).as_posix().encode("utf-8"))
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)


def base_source_fingerprint(source_dir: str | Path) -> str:
    root = Path(source_dir)
    paths = sorted(root.glob("*.designspace"))
    for ufo_dir in sorted(root.glob("*.ufo")):
        paths.extend(sorted(path for path in ufo_dir.rglob("*") if path.is_file()))
    paths.extend(sorted((root / "features").glob("*.fea")))

    hasher = hashlib.sha256()
    for path in paths:
        _hash_file(hasher, path, root)
    return hasher.hexdigest()


def base_cache_identity(
    font_config: ResolvedConfig,
    runtime_context: BuildRuntimeContext,
) -> dict[str, Any]:
    record = font_config.to_build_record()
    for key in ("formats", "nerd_font", "cjk_format", "cjk"):
        record.pop(key, None)
    return {
        "schema": 1,
        "config": record,
        "sources": base_source_fingerprint(runtime_context.src_dir),
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

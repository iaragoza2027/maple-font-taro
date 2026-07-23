from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.cjk.config import CJKBuildConfig
from scripts.cjk.resolver import serialize_cjk_build_config
from scripts.font_ops.fonttools import TTFont
from scripts.font_ops.names import FontNameConfig


CJK_VARIABLE_CACHE_SCHEMA = 1
CJK_VARIABLE_MANIFEST = "variable-cache.json"


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def cjk_variable_cache_identity(
    config: CJKBuildConfig,
    font_config: FontNameConfig,
) -> dict[str, Any]:
    return {
        "schema": CJK_VARIABLE_CACHE_SCHEMA,
        "config": serialize_cjk_build_config(config),
        "source": _file_digest(config.source.path),
        "feature_font": _file_digest(config.feature_font_path),
        "font": {
            "version": font_config.version_str,
            "beta": font_config.beta,
            "feature_freeze": font_config.freeze_config_str,
        },
    }


def cjk_variable_manifest_path(config: CJKBuildConfig) -> Path:
    return config.output.dir / CJK_VARIABLE_MANIFEST


def _is_readable_font(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        font = TTFont(path, lazy=True)
        font.close()
    except Exception:
        return False
    return True


def has_valid_cjk_variable_cache(
    config: CJKBuildConfig,
    font_config: FontNameConfig,
) -> bool:
    regular_path = config.output.dir / config.output.regular_variable
    italic_path = config.output.dir / config.output.italic_variable
    manifest_path = cjk_variable_manifest_path(config)
    if not _is_readable_font(regular_path) or not _is_readable_font(italic_path):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return manifest == cjk_variable_cache_identity(config, font_config)


def write_cjk_variable_manifest(
    config: CJKBuildConfig,
    font_config: FontNameConfig,
) -> Path:
    manifest_path = cjk_variable_manifest_path(config)
    temporary = manifest_path.with_name(f".{manifest_path.name}.tmp")
    temporary.write_text(
        json.dumps(cjk_variable_cache_identity(config, font_config), indent=2),
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return manifest_path

from __future__ import annotations

from pathlib import Path

from scripts.cjk.config import CJKBuildConfig
from scripts.utils.files import get_directory_hash


def static_hash_path(config: CJKBuildConfig) -> Path:
    """Return the sidecar hash path for a generated static base."""
    return config.output.dir / config.output.static_hash


def write_static_hash(config: CJKBuildConfig, static_dir: Path) -> None:
    """Write one directory digest for the complete static CJK stage."""
    digest = get_directory_hash(str(static_dir))
    hash_path = static_hash_path(config)
    hash_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = hash_path.with_name(f".{hash_path.name}.tmp")
    temporary.write_text(f"{digest}\n", encoding="utf-8")
    temporary.replace(hash_path)


def has_valid_cjk_static_cache(
    config: CJKBuildConfig,
    static_dir: Path,
    required_styles: set[str],
) -> bool:
    """Validate required static styles and the stage-level directory digest."""
    if not static_dir.is_dir():
        return False

    prefix = f"{config.naming.static_file_prefix}-"
    available_styles = {
        path.stem.removeprefix(prefix)
        for path in static_dir.glob("*.ttf")
        if path.name.startswith(prefix)
    }
    if not required_styles.issubset(available_styles):
        return False

    hash_path = static_hash_path(config)
    if not hash_path.is_file():
        return False
    try:
        expected = hash_path.read_text(encoding="utf-8").strip()
        actual = get_directory_hash(str(static_dir))
    except Exception:
        return False
    return bool(expected) and expected == actual

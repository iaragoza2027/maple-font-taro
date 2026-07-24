from __future__ import annotations

from pathlib import Path

from scripts.cjk.config import CJKBuildConfig
from scripts.font_ops.fonttools import TTFont


def _is_readable_font(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        with path.open("rb") as source:
            font = TTFont(source, lazy=True)
            font.close()
    except Exception:
        return False
    return True


def has_valid_cjk_variable_cache(
    config: CJKBuildConfig,
) -> bool:
    regular_path = config.output.dir / config.output.regular_variable
    italic_path = config.output.dir / config.output.italic_variable
    return _is_readable_font(regular_path) and _is_readable_font(italic_path)

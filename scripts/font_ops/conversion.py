from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fontTools.ttLib import TTFont

from scripts.utils.logging import logger


WebFontFlavor = Literal["woff", "woff2"]


def _convert_font_to_web(
    font_path: Path,
    target_dir: Path,
    flavor: WebFontFlavor,
) -> Path:
    target_path = target_dir / f"{font_path.name}.{flavor}"
    font = TTFont(font_path, recalcTimestamp=False)
    try:
        font.flavor = flavor
        font.save(target_path, reorderTables=False)
    finally:
        font.close()
    logger.info("Saved %s font to %s", flavor.upper(), target_path)
    return target_path


def convert_to_web(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    flavor: WebFontFlavor = "woff2",
) -> list[Path]:
    """Convert an SFNT font or a flat directory of fonts to WOFF or WOFF2."""
    source = Path(input_path)
    font_paths = (
        [source]
        if source.is_file()
        else sorted(
            path
            for path in source.iterdir()
            if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
        )
    )
    if not font_paths:
        raise FileNotFoundError(f"No SFNT fonts found in {source}")

    target_dir = (
        Path(output_dir)
        if output_dir is not None
        else source.parent
        if source.is_file()
        else source
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=min(len(font_paths), 4)) as executor:
        outputs = list(
            executor.map(
                _convert_font_to_web,
                font_paths,
                [target_dir] * len(font_paths),
                [flavor] * len(font_paths),
            )
        )

    return outputs

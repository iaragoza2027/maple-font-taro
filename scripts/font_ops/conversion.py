from __future__ import annotations

from pathlib import Path
from typing import Literal

from fontTools.ttLib import TTFont


WebFontFlavor = Literal["woff", "woff2"]


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
    outputs: list[Path] = []

    for font_path in font_paths:
        target_path = target_dir / f"{font_path.name}.{flavor}"
        font = TTFont(font_path, recalcTimestamp=False)
        try:
            font.flavor = flavor
            font.save(target_path, reorderTables=False)
        finally:
            font.close()
        outputs.append(target_path)

    return outputs

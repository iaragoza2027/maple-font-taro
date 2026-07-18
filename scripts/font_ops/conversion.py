from __future__ import annotations

from concurrent.futures import Executor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fontTools.ttLib import TTFont

from scripts.utils.logging import logger, set_log_task
from scripts.utils.process import create_process_executor, run_jobs


WebFontFlavor = Literal["woff", "woff2"]


@dataclass(frozen=True, slots=True)
class WebFontConversionJob:
    font_path: Path
    target_dir: Path
    flavor: WebFontFlavor


def _convert_font_to_web(
    job: WebFontConversionJob,
) -> Path:
    set_log_task(job.flavor)
    target_path = job.target_dir / f"{job.font_path.name}.{job.flavor}"
    font = TTFont(job.font_path, recalcTimestamp=False)
    try:
        font.flavor = job.flavor
        font.save(target_path, reorderTables=False)
    finally:
        font.close()
    logger.info("Saved %s font to %s", job.flavor.upper(), target_path)
    return target_path


def convert_to_web(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    flavor: WebFontFlavor = "woff2",
    executor: Executor | None = None,
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
    jobs = [WebFontConversionJob(path, target_dir, flavor) for path in font_paths]
    if executor is not None:
        return run_jobs(executor, _convert_font_to_web, jobs)

    with create_process_executor(
        min(len(font_paths), 4), fallback_to_threads=True
    ) as process_executor:
        return run_jobs(process_executor, _convert_font_to_web, jobs)

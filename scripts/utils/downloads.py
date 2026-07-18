from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

from scripts.utils.logging import log_progress, logger


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{size} B"
        value /= 1024
    raise AssertionError("unreachable")


def _download_progress_message(
    target_path: str | Path,
    downloaded_size: int,
    total_size: int,
) -> str:
    percentage = min(downloaded_size * 100 // total_size, 100)
    return (
        f"Downloading {Path(target_path).name}: {percentage:3d}% "
        f"({_format_size(downloaded_size)} / {_format_size(total_size)})"
    )


def download_file(url: str, target_path: str | Path) -> None:
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request) as response, Path(target_path).open("wb") as output:
        downloaded_size = 0
        try:
            total_size = int(response.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            total_size = 0
        last_percentage = -1
        progress_message: str | None = None
        if total_size > 0:
            progress_message = _download_progress_message(target_path, 0, total_size)
            log_progress(progress_message)
            last_percentage = 0
        try:
            while chunk := response.read(8192):
                output.write(chunk)
                downloaded_size += len(chunk)
                if total_size <= 0:
                    continue
                percentage = min(downloaded_size * 100 // total_size, 100)
                if percentage == last_percentage or percentage == 100:
                    continue
                last_percentage = percentage
                progress_message = _download_progress_message(
                    target_path,
                    downloaded_size,
                    total_size,
                )
                log_progress(progress_message)
        finally:
            if total_size > 0:
                progress_message = _download_progress_message(
                    target_path,
                    downloaded_size,
                    total_size,
                )
                log_progress(progress_message, complete=True)
    logger.info("Downloaded file: path=%s, bytes=%s", target_path, downloaded_size)


def download_zip_and_extract(
    name: str,
    url: str,
    zip_path: str | Path,
    output_dir: str | Path,
    remove_zip: bool = False,
) -> bool:
    archive_path = Path(zip_path)
    if not archive_path.exists():
        logger.info("Download archive: name=%s, url=%s", name, url)
        try:
            download_file(url, archive_path)
        except Exception as error:
            logger.error(
                "Failed to download archive: name=%s, url=%s, error=%s",
                name,
                url,
                error,
            )
            return False
    try:
        with ZipFile(archive_path, "r") as zip_file:
            zip_file.extractall(output_dir)
        if remove_zip:
            archive_path.unlink()
        return True
    except Exception as error:
        logger.error("Failed to extract archive: name=%s, error=%s", name, error)
        return False


def check_font_patcher(
    version: str,
    github_mirror: str = "github.com",
    target_dir: str | Path = "FontPatcher",
) -> bool:
    target_path = Path(target_dir)
    patcher_path = target_path / "font-patcher"
    if target_path.exists():
        if f"# Nerd Fonts Version: {version}" in patcher_path.read_text(
            encoding="utf-8"
        ):
            return True
        logger.info("Remove mismatched FontPatcher version: path=%s", target_path)
        shutil.rmtree(target_path, ignore_errors=True)

    zip_path = Path("FontPatcher.zip")
    url = (
        f"https://{github_mirror}/ryanoasis/nerd-fonts/releases/"
        f"download/v{version}/{zip_path.name}"
    )
    if not download_zip_and_extract(
        name="Nerd Font Patcher",
        url=url,
        zip_path=zip_path,
        output_dir=target_path,
    ):
        return False

    if f"# Nerd Fonts Version: {version}" in patcher_path.read_text(encoding="utf-8"):
        return True

    logger.error("FontPatcher version mismatch: version=%s, url=%s", version, url)
    return False


def github_host(default: str) -> str:
    return os.environ.get("GITHUB", default)

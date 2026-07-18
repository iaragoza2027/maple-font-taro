from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

from scripts.common.process import is_ci


def download_file(url: str, target_path: str | Path) -> None:
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request) as response, Path(target_path).open("wb") as output:
        total_size = int(response.getheader("Content-Length").strip())
        downloaded_size = 0
        while chunk := response.read(8192):
            output.write(chunk)
            if not is_ci():
                downloaded_size += len(chunk)
                percent = downloaded_size / total_size * 100
                print(
                    f"Downloading: [{percent:.2f}%] {downloaded_size} / {total_size}",
                    end="\r",
                )


def download_zip_and_extract(
    name: str,
    url: str,
    zip_path: str | Path,
    output_dir: str | Path,
    remove_zip: bool = False,
) -> bool:
    archive_path = Path(zip_path)
    if not archive_path.exists():
        print(f"{name} does not exist, download from {url}")
        try:
            download_file(url, archive_path)
        except Exception as error:
            print(
                f"❗\nFail to download {name}. Please check your internet "
                f"connection or download it manually from {url}, then put "
                "downloaded zip into project's root and run this script again. "
                f"\n    Error: {error}"
            )
            return False
    try:
        with ZipFile(archive_path, "r") as zip_file:
            zip_file.extractall(output_dir)
        if remove_zip:
            archive_path.unlink()
        return True
    except Exception as error:
        print(f"❗Fail to extract {name}. Error: {error}")
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
        print("FontPatcher version not match, delete it")
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

    print(f"❗FontPatcher version is not {version}, please download it from {url}")
    return False


def github_host(default: str) -> str:
    return os.environ.get("GITHUB", default)

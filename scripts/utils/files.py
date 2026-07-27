from __future__ import annotations

import json
from collections.abc import Callable
import hashlib
from os import path, walk
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZipFile

from scripts.utils.logging import logger


def join_path(*parts: str | Path) -> str:
    if not parts:
        raise ValueError("At least one path part is required")
    result = Path(parts[0])
    for part in parts[1:]:
        result /= part
    return str(result)


def write_text(
    file_path: str | Path,
    content: str,
    mode: str = "w",
) -> None:
    if not isinstance(content, str):
        raise ValueError("Invalid content")
    with Path(file_path).open(encoding="utf-8", mode=mode, newline="\n") as file:
        file.write(content)


def write_json(file_path: str | Path, data: dict[str, Any]) -> None:
    with Path(file_path).open("w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, indent=2)


def read_json(file_path: str | Path) -> dict[str, Any]:
    with Path(file_path).open("r", encoding="utf-8") as file:
        return json.load(file)


def read_text(file_path: str | Path) -> str:
    return Path(file_path).read_text(encoding="utf-8")


def archive(
    source: str | Path,
    target: str | Path,
    include: Callable[[str], bool],
) -> None:
    source_path = Path(source)
    with ZipFile(target, "w", compression=ZIP_BZIP2, compresslevel=9) as zip_file:
        for child in source_path.iterdir():
            if include(str(child)):
                zip_file.write(child, child.name)
    logger.info("Created archive: path=%s", target)


def archive_fonts(
    source_file_or_dir_path: str,
    target_parent_dir_path: str,
    family_name_compact: str,
    suffix: str,
    build_config_path: str,
) -> tuple[str, str]:
    source_folder_name = path.basename(source_file_or_dir_path)
    archive_label = archive_output_label(source_folder_name)
    zip_name_without_ext = f"{family_name_compact}-{archive_label}{suffix}"
    zip_path = join_path(target_parent_dir_path, f"{zip_name_without_ext}.zip")

    font_files: list[str] = []
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED, compresslevel=5) as zip_file:
        for root, _, files in walk(source_file_or_dir_path):
            for file_name in files:
                file_path = join_path(root, file_name)
                relative_path = path.relpath(file_path, source_file_or_dir_path)
                if relative_path == "README.md":
                    continue
                zip_file.write(
                    file_path,
                    relative_path,
                )
                if Path(file_name).suffix.lower() in {".otf", ".ttf", ".woff2"}:
                    font_files.append(Path(relative_path).as_posix())
        zip_file.writestr(
            "README.md",
            archive_font_readme(zip_name_without_ext, font_files),
        )
        zip_file.write("OFL.txt", "LICENSE.txt")
        if not source_folder_name.startswith("Variable"):
            zip_file.write(build_config_path, "config.json")

    sha256 = hashlib.sha256()
    with Path(zip_path).open("rb") as zip_file:
        while data := zip_file.read(1024):
            sha256.update(data)
    return sha256.hexdigest(), zip_name_without_ext


def archive_output_label(source_folder_name: str) -> str:
    if source_folder_name == "Variable":
        return "VF"
    if source_folder_name.startswith("Variable-"):
        return f"{source_folder_name.removeprefix('Variable-')}-VF"
    return source_folder_name


def archive_font_readme(archive_name: str, font_files: list[str]) -> str:
    lines = [f"# {archive_name}", "", "## Font Files", ""]
    lines.extend(
        f"- [{font_file}](./{quote(font_file, safe='/')})"
        for font_file in sorted(font_files)
    )
    return "\n".join(lines) + "\n"


def get_directory_hash(dir_path: str) -> str:
    hasher = hashlib.sha256()
    for root, _, files in sorted(walk(dir_path)):
        for file_name in sorted(files):
            file_path = path.join(root, file_name)
            try:
                with open(file_path, "rb") as file:
                    while data := file.read(4096):
                        hasher.update(data)
            except (IOError, OSError) as error:
                raise Exception(f"Error reading file: {file_path} - {error}") from error
    return hasher.hexdigest()

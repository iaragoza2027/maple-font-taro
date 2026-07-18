from __future__ import annotations

import json
from collections.abc import Callable
import hashlib
from os import path, walk
from pathlib import Path
from typing import Any
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZipFile


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
    print(f"📦 Package {target}")


def archive_fonts(
    source_file_or_dir_path: str,
    target_parent_dir_path: str,
    family_name_compact: str,
    suffix: str,
    build_config_path: str,
) -> tuple[str, str]:
    source_folder_name = path.basename(source_file_or_dir_path)
    zip_name_without_ext = f"{family_name_compact}-{source_folder_name}{suffix}"
    zip_path = join_path(target_parent_dir_path, f"{zip_name_without_ext}.zip")

    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED, compresslevel=5) as zip_file:
        for root, _, files in walk(source_file_or_dir_path):
            for file_name in files:
                file_path = join_path(root, file_name)
                zip_file.write(
                    file_path,
                    path.relpath(file_path, source_file_or_dir_path),
                )
        zip_file.write("OFL.txt", "LICENSE.txt")
        if not source_file_or_dir_path.endswith("Variable"):
            zip_file.write(build_config_path, "config.json")

    sha256 = hashlib.sha256()
    with Path(zip_path).open("rb") as zip_file:
        while data := zip_file.read(1024):
            sha256.update(data)
    return sha256.hexdigest(), zip_name_without_ext


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


def check_directory_hash(dir_path: str) -> bool:
    if not path.exists(dir_path):
        print(f"{dir_path} not exist, skip computing hash")
        return False
    with open(f"{dir_path}.sha256", encoding="utf-8") as hash_file:
        return hash_file.readline() == get_directory_hash(dir_path)

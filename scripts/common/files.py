from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zipfile import ZIP_BZIP2, ZipFile


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

from __future__ import annotations

import hashlib
import json
import stat
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def hash_bytes(data: bytes) -> str:
    """Return the SHA-256 checksum of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _require_regular_file(path: Path) -> None:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"Hash input must not be a symbolic link: {path}")
    if not stat.S_ISREG(mode):
        raise ValueError(f"Hash input must be a regular file: {path}")


def hash_file(path: Path) -> str:
    """Return the SHA-256 checksum of a regular file's contents."""
    _require_regular_file(path)
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_files(files: Mapping[str, Path]) -> str:
    """Hash file contents in key order without including the keys themselves."""
    hasher = hashlib.sha256()
    for _, path in sorted(files.items(), key=lambda item: item[0]):
        hasher.update(bytes.fromhex(hash_file(path)))
    return hasher.hexdigest()


def hash_directory(directory: Path) -> str:
    """Hash a directory's files using relative names only for ordering."""
    mode = directory.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"Hash directory must not be a symbolic link: {directory}")
    if not stat.S_ISDIR(mode):
        raise ValueError(f"Hash directory must be a directory: {directory}")

    files = {
        path.relative_to(directory).as_posix(): path
        for path in directory.rglob("*")
        if not stat.S_ISDIR(path.lstat().st_mode)
    }
    return hash_files(files)


def hash_json(value: object) -> str:
    """Hash a value using deterministic compact JSON serialization."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hash_bytes(payload)

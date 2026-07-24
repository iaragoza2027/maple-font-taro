from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.utils.logging import logger


CACHE_SCHEMA = 1
CACHE_FILE_NAME = "build-cache.json"


def cache_record_path(output_root: str | Path) -> Path:
    return Path(output_root) / CACHE_FILE_NAME


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def stage_identity(build_identity: dict[str, Any], stage: str) -> str:
    return _digest({"build": build_identity, "stage": stage})


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def relative_cache_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def output_snapshot(
    root: Path,
    stage: str,
    paths: list[Path],
) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for path in sorted(paths):
        if not path.is_file():
            continue
        stat = path.stat()
        relative = relative_cache_path(root, path)
        digest = file_hash(path)
        snapshot[relative] = {
            "sha256": digest,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
        logger.debug(
            "Cache file: stage=%s, path=%s, size=%s, mtime_ns=%s, sha256=%s",
            stage,
            relative,
            stat.st_size,
            stat.st_mtime_ns,
            digest,
        )
    return snapshot


def read_cache_record(root: Path) -> dict[str, Any] | None:
    path = cache_record_path(root)
    if not path.is_file():
        logger.info("Cache record: path=%s, status=missing", CACHE_FILE_NAME)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.info("Cache record: path=%s, status=invalid", CACHE_FILE_NAME)
        return None
    if (
        not isinstance(data, dict)
        or data.get("schema") != CACHE_SCHEMA
        or not isinstance(data.get("identity"), dict)
        or not isinstance(data.get("stages"), dict)
    ):
        logger.info("Cache record: path=%s, status=invalid", CACHE_FILE_NAME)
        return None
    logger.info("Cache record: path=%s, status=found", CACHE_FILE_NAME)
    return data


def write_cache_record(root: Path, record: dict[str, Any]) -> None:
    path = cache_record_path(root)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def validate_stage(
    root: Path,
    record: dict[str, Any] | None,
    stage: str,
    identity: str,
    expected_paths: list[Path],
) -> bool:
    stages = (record or {}).get("stages")
    stage_record = stages.get(stage) if isinstance(stages, dict) else None
    if not isinstance(stage_record, dict):
        logger.info("Cache validation: stage=%s, status=miss", stage)
        logger.info("Cache invalidation: stage=%s, reason=missing-record", stage)
        return False
    if stage_record.get("identity") != identity:
        logger.info("Cache validation: stage=%s, status=miss", stage)
        logger.info("Cache invalidation: stage=%s, reason=identity-changed", stage)
        return False
    files = stage_record.get("files")
    if not isinstance(files, dict):
        logger.info("Cache validation: stage=%s, status=miss", stage)
        logger.info("Cache invalidation: stage=%s, reason=invalid-record", stage)
        return False
    expected = {relative_cache_path(root, path) for path in expected_paths}
    if not expected.issubset(files):
        logger.info("Cache validation: stage=%s, status=miss", stage)
        logger.info("Cache invalidation: stage=%s, reason=missing-output", stage)
        return False
    for path in expected_paths:
        metadata = files[relative_cache_path(root, path)]
        if not isinstance(metadata, dict):
            logger.info("Cache validation: stage=%s, status=miss", stage)
            logger.info("Cache invalidation: stage=%s, reason=invalid-record", stage)
            return False
        if not path.is_file() or path.stat().st_size == 0:
            logger.info("Cache validation: stage=%s, status=miss", stage)
            logger.info("Cache invalidation: stage=%s, reason=missing-output", stage)
            return False
        stat = path.stat()
        logger.debug(
            "Cache file: stage=%s, path=%s, size=%s, mtime_ns=%s, sha256=%s",
            stage,
            relative_cache_path(root, path),
            stat.st_size,
            stat.st_mtime_ns,
            metadata.get("sha256"),
        )
        if (
            metadata.get("size") != stat.st_size
            or metadata.get("mtime_ns") != stat.st_mtime_ns
        ):
            if metadata.get("sha256") != file_hash(path):
                logger.info("Cache validation: stage=%s, status=miss", stage)
                logger.info("Cache invalidation: stage=%s, reason=hash-mismatch", stage)
                return False
    logger.info("Cache validation: stage=%s, status=hit", stage)
    return True

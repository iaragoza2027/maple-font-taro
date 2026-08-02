from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any
from zipfile import BadZipFile, ZipFile

from scripts.cjk.builder import build_cjk_fonts
from scripts.cjk.presets import build_preset_config, list_presets
from scripts.config.resolver import resolve_default_build_config
from scripts.utils.downloads import github_mirror_from_config


MANIFEST_SCHEMA = 1
DEFAULT_MANIFEST = Path(".cjk-base-manifest.json")
DEFAULT_ARTIFACT_DIR = Path("cjk-base-artifacts")
DEFAULT_CANDIDATE_DIR = Path("cjk-base-candidate")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VERSION_PATTERNS = (
    re.compile(r"/releases/download/([^/]+)/"),
    re.compile(r"/raw/([^/]+)/"),
)


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser(
        "cjk-base", help="Plan, build, and publish reusable CJK base fonts"
    )
    actions = parser.add_subparsers(dest="cjk_base_action", required=True)

    matrix = actions.add_parser("matrix", help="Print the changed locale matrix")
    matrix.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    matrix.add_argument("--force-all", action="store_true")

    build = actions.add_parser("build", help="Build one reusable CJK base")
    build.add_argument("locale", choices=list(list_presets()))
    build.add_argument("--output", type=Path, default=DEFAULT_ARTIFACT_DIR)

    assemble = actions.add_parser(
        "assemble", help="Assemble matrix artifacts into a publish candidate"
    )
    assemble.add_argument("--baseline", type=Path, default=DEFAULT_MANIFEST)
    assemble.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_DIR)
    assemble.add_argument("--output", type=Path, default=DEFAULT_CANDIDATE_DIR)

    verify = actions.add_parser("verify", help="Verify a publish candidate")
    verify.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE_DIR)

    notes = actions.add_parser("notes", help="Render cjk-base release notes")
    notes.add_argument(
        "--manifest", type=Path, default=DEFAULT_CANDIDATE_DIR / "manifest.json"
    )
    notes.add_argument("--output", type=Path, default=Path("cjk-base-notes.md"))
    return parser


def run(args: argparse.Namespace) -> None:
    action = args.cjk_base_action
    if action == "matrix":
        print(
            json.dumps(
                {
                    "include": [
                        {"locale": locale}
                        for locale in changed_locales(args.manifest, args.force_all)
                    ]
                },
                separators=(",", ":"),
            )
        )
        return
    if action == "build":
        build_locale(args.locale, args.output)
        return
    if action == "assemble":
        assemble_candidate(args.baseline, args.artifacts, args.output)
        return
    if action == "verify":
        verify_candidate(args.candidate)
        return
    if action == "notes":
        write_release_notes(args.manifest, args.output)
        return
    raise ValueError(f"Unknown cjk-base action: {action}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_inputs(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted({path for path in paths if path.is_file()}):
        relative = path.as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _tracked_input_paths(locale: str) -> list[Path]:
    common: list[Path] = []
    for root in (
        Path("scripts/cjk"),
        Path("scripts/config"),
        Path("scripts/font_ops"),
        Path("scripts/utils"),
        Path("source/features"),
    ):
        common.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
    common.extend(
        path
        for path in (
            Path("config.json"),
            Path("pyproject.toml"),
            Path("uv.lock"),
            Path("source/cjk/variable-source/MapleMono-CJK-Base-VF.ttf"),
            Path(f"source/cjk/{locale}/config-{locale}.json"),
        )
        if path.is_file()
    )
    return common


def input_fingerprint(locale: str) -> str:
    return _hash_inputs(_tracked_input_paths(locale))


def _hash_path(locale: str) -> Path:
    return Path("source/cjk") / locale / f"static-{locale}.sha256"


def _archive_name(locale: str) -> str:
    return f"{locale}-base-static.zip"


def _source_url(locale: str) -> str:
    config = build_preset_config(locale)  # type: ignore[arg-type]
    if config.source.download is None:
        raise ValueError(f"CJK preset {locale} has no source download URL")
    return config.source.download.url


def source_ref(url: str) -> str:
    for pattern in VERSION_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return url


def _read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != MANIFEST_SCHEMA:
        return None
    locales = data.get("locales")
    if not isinstance(locales, dict):
        return None
    return data


def _current_hash(locale: str) -> str | None:
    path = _hash_path(locale)
    if not path.is_file():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value if HASH_PATTERN.fullmatch(value) else None


def changed_locales(manifest_path: Path, force_all: bool = False) -> tuple[str, ...]:
    locales = tuple(list_presets())
    manifest = _read_manifest(manifest_path)
    if force_all or manifest is None:
        return locales
    previous = manifest["locales"]
    changed: list[str] = []
    for locale in locales:
        entry = previous.get(locale)
        if not isinstance(entry, dict):
            changed.append(locale)
            continue
        if entry.get("input_fingerprint") != input_fingerprint(locale):
            changed.append(locale)
            continue
        if entry.get("static_sha256") != _current_hash(locale):
            changed.append(locale)
    return tuple(changed)


def build_locale(locale: str, output_root: Path) -> None:
    if locale not in list_presets():
        raise ValueError(f"Unsupported CJK locale: {locale}")
    config = build_preset_config(locale)  # type: ignore[arg-type]
    build_cjk_fonts(
        config,
        resolve_default_build_config(),
        github_mirror=github_mirror_from_config(),
    )
    archive_path = config.output.dir / config.output.archive_name
    hash_path = config.output.dir / config.output.static_hash
    if not archive_path.is_file() or not hash_path.is_file():
        raise FileNotFoundError(f"CJK base build did not produce {locale} artifacts")
    output_dir = output_root / locale
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True)
    target_archive = output_dir / _archive_name(locale)
    target_hash = output_dir / hash_path.name
    shutil.copy2(archive_path, target_archive)
    shutil.copy2(hash_path, target_hash)
    _validate_archive(target_archive)
    static_hash = target_hash.read_text(encoding="utf-8").strip()
    if not HASH_PATTERN.fullmatch(static_hash):
        raise ValueError(f"Invalid static hash for {locale}")
    metadata = {
        "locale": locale,
        "archive_name": target_archive.name,
        "archive_sha256": _sha256(target_archive),
        "static_sha256": static_hash,
        "input_fingerprint": input_fingerprint(locale),
        "source_url": _source_url(locale),
        "source_ref": source_ref(_source_url(locale)),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _validate_archive(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            if not names or any(
                name.startswith(("/", "\\")) or ".." in Path(name).parts
                for name in names
            ):
                raise ValueError(f"Invalid archive members: {path}")
            bad = archive.testzip()
    except BadZipFile as error:
        raise ValueError(f"Invalid ZIP archive: {path}") from error
    if bad is not None:
        raise ValueError(f"Corrupt ZIP member {bad!r}: {path}")


def assemble_candidate(
    baseline_path: Path, artifacts_root: Path, output_root: Path
) -> None:
    changed = [
        path for path in artifacts_root.glob("*/metadata.json") if path.is_file()
    ]
    if not changed:
        raise ValueError("No changed CJK base artifacts were produced")
    baseline = _read_manifest(baseline_path)
    locales: dict[str, Any] = {}
    if baseline is not None:
        locales.update(baseline["locales"])
    output_root.mkdir(parents=True, exist_ok=True)
    asset_root = output_root / "assets"
    hash_root = output_root / "hashes"
    asset_root.mkdir(exist_ok=True)
    hash_root.mkdir(exist_ok=True)
    changed_entries: list[dict[str, Any]] = []
    for metadata_path in sorted(changed):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        locale = metadata.get("locale")
        if locale not in list_presets():
            raise ValueError(f"Invalid locale metadata: {locale!r}")
        locale_root = metadata_path.parent
        archive = locale_root / metadata["archive_name"]
        hash_path = locale_root / f"static-{locale}.sha256"
        if not archive.is_file() or not hash_path.is_file():
            raise FileNotFoundError(f"Incomplete CJK base artifact: {locale}")
        _validate_archive(archive)
        if metadata["archive_sha256"] != _sha256(archive):
            raise ValueError(f"Archive digest mismatch: {locale}")
        if metadata["static_sha256"] != hash_path.read_text(encoding="utf-8").strip():
            raise ValueError(f"Static hash mismatch: {locale}")
        shutil.copy2(archive, asset_root / archive.name)
        shutil.copy2(hash_path, hash_root / hash_path.name)
        locales[locale] = metadata
        changed_entries.append(metadata)
    candidate = {
        "schema": MANIFEST_SCHEMA,
        "baseline_manifest_sha256": _sha256(baseline_path)
        if baseline_path.is_file()
        else "",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "locales": {locale: locales[locale] for locale in sorted(locales)},
    }
    (output_root / "manifest.json").write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_root / "changed.json").write_text(
        json.dumps(
            {
                "locales": [entry["locale"] for entry in changed_entries],
                "entries": changed_entries,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def verify_candidate(candidate_root: Path) -> None:
    manifest = _read_manifest(candidate_root / "manifest.json")
    if manifest is None:
        raise ValueError("Candidate manifest is missing or invalid")
    changed_path = candidate_root / "changed.json"
    changed_data = json.loads(changed_path.read_text(encoding="utf-8"))
    entries = changed_data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Candidate has no changed entries")
    for entry in entries:
        locale = entry.get("locale")
        if locale not in list_presets():
            raise ValueError(f"Invalid candidate locale: {locale!r}")
        archive = candidate_root / "assets" / entry["archive_name"]
        if not archive.is_file() or _sha256(archive) != entry["archive_sha256"]:
            raise ValueError(f"Candidate archive is missing or corrupt: {locale}")
        _validate_archive(archive)
        hash_path = _hash_path(locale)
        if (
            not hash_path.is_file()
            or hash_path.read_text(encoding="utf-8").strip() != entry["static_sha256"]
        ):
            raise ValueError(f"Current branch hash does not match candidate: {locale}")
        if input_fingerprint(locale) != entry["input_fingerprint"]:
            raise ValueError(f"Current branch inputs changed after build: {locale}")


def write_release_notes(manifest_path: Path, output_path: Path) -> None:
    manifest = _read_manifest(manifest_path)
    if manifest is None:
        raise ValueError("Manifest is missing or invalid")
    lines = [
        "# CJK Base Fonts",
        "",
        f"Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} UTC",
        "",
        "| Locale | Source version | Source URL | Built | Static hash |",
        "| --- | --- | --- | --- | --- |",
    ]
    for locale in list(list_presets()):
        entry = manifest["locales"].get(locale)
        if not isinstance(entry, dict):
            continue
        lines.append(
            f"| {locale.upper()} | `{entry['source_ref']}` | "
            f"[{entry['source_url']}]({entry['source_url']}) | "
            f"{entry['built_at']} | `{entry['static_sha256']}` |"
        )
    lines.extend(
        [
            "",
            "The archives are reusable static CJK bases generated by `task.py cjk-base`.",
            "The source URLs are maintained manually in the repository presets.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")

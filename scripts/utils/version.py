from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_SECTION_PATTERN = re.compile(
    r"^\[project\]\s*$"
    r"(?P<section>.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
VERSION_PATTERN = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"\s*$', re.MULTILINE)
PROJECT_VERSION_PATTERN = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)(?:b(?P<beta>\d+))?$"
)
FONT_VERSION_PATTERN = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d{3})$")
TAG_PATTERN = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)"
    r"(?:-beta(?:\.)?(?P<beta>\d+))?$"
)


@dataclass(frozen=True, slots=True)
class ParsedVersion:
    major: int
    minor: int
    beta: int | None = None

    @property
    def core(self) -> str:
        return f"{self.major}.{self.minor}"

    @property
    def project(self) -> str:
        return self.core if self.beta is None else f"{self.core}b{self.beta}"

    @property
    def tag(self) -> str:
        return self.core if self.beta is None else f"{self.core}-beta.{self.beta}"


def parse_project_version(version: str) -> ParsedVersion:
    match = PROJECT_VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(
            f"Expected a PEP 440 project version like 8.0 or 8.0b1, got: {version}"
        )
    beta = match.group("beta")
    return ParsedVersion(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        beta=int(beta) if beta is not None else None,
    )


def parse_version_tag(tag: str) -> ParsedVersion:
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ValueError(f"Expected a tag like v8.0 or v8.0-beta.1, got: {tag}")
    beta = match.group("beta")
    return ParsedVersion(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        beta=int(beta) if beta is not None else None,
    )


def parse_font_version(version: str) -> tuple[int, int]:
    match = FONT_VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(
            f"Expected a font version like 8.001 with three fractional digits, got: {version}"
        )
    return int(match.group("major")), int(match.group("minor"))


def font_version_for_core(core: str) -> str:
    parsed = parse_project_version(core)
    minor = str(parsed.minor)
    if len(minor) > 3:
        raise ValueError(f"Project minor version does not fit a font version: {core}")
    return f"{parsed.major}.{minor.ljust(3, '0')}"


def project_version_from_font_version(version: str) -> str:
    major, minor = parse_font_version(version)
    return f"{major}.{minor // 100}"


def project_version() -> str:
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    try:
        pyproject = pyproject_path.read_text(encoding="utf-8")
        project_section = PROJECT_SECTION_PATTERN.search(pyproject)
        if project_section is None:
            raise ValueError("pyproject.toml is missing the [project] section")
        version = VERSION_PATTERN.search(project_section.group("section"))
        if version is None:
            raise ValueError("pyproject.toml [project] section is missing version")
        return parse_project_version(version.group("version")).project
    except (OSError, ValueError):
        config_path = PROJECT_ROOT / "config.json"
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return project_version_from_font_version(str(data["font_version"]))
        except (
            OSError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            raise ValueError(
                "Unable to read project version from pyproject.toml or config.json"
            ) from error


def version_tag(version: str | None = None) -> str:
    return f"v{parse_project_version(version or project_version()).tag}"

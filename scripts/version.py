from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SECTION_PATTERN = re.compile(
    r"^\[project\]\s*$"
    r"(?P<section>.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
VERSION_PATTERN = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"\s*$', re.MULTILINE)


def project_version() -> str:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_section = PROJECT_SECTION_PATTERN.search(pyproject)
    if project_section is None:
        raise ValueError("pyproject.toml is missing the [project] section")
    version = VERSION_PATTERN.search(project_section.group("section"))
    if version is None:
        raise ValueError("pyproject.toml [project] section is missing version")
    return version.group("version")


def version_tag() -> str:
    return f"v{project_version()}"

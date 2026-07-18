from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


CI_ENVIRONMENTS = (
    "JENKINS_HOME",
    "TRAVIS",
    "CIRCLECI",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "TF_BUILD",
)


def is_ci() -> bool:
    return any(os.environ.get(name) for name in CI_ENVIRONMENTS)


def run(
    command: str | list[str],
    extra_args: list[str] | None = None,
    log: bool | None = None,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    args = command.split() if isinstance(command, str) else list(command)
    args.extend(extra_args or ())
    should_log = not is_ci() if log is None else log
    return subprocess.run(
        args,
        cwd=cwd,
        stdout=None if should_log else subprocess.DEVNULL,
        stderr=None if should_log else subprocess.DEVNULL,
        check=True,
        text=True,
    )


def get_font_forge_bin() -> str | None:
    platform_paths = {
        "win32": Path("C:/Program Files (x86)/FontForgeBuilds/bin/fontforge.exe"),
        "darwin": Path(
            "/Applications/FontForge.app/Contents/Resources/opt/local/bin/fontforge"
        ),
    }
    candidate = platform_paths.get(sys.platform, Path("/usr/bin/fontforge"))
    if candidate.exists():
        return str(candidate)
    return shutil.which("fontforge")

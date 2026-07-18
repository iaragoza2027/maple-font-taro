from __future__ import annotations

import importlib.util

from scripts.utils.errors import BuildDependencyError


def check_ftcli() -> None:
    package_name_v1 = "foundryToolsCLI"
    package_name_v2 = "foundrytools_cli"
    package_spec_v1 = importlib.util.find_spec(package_name_v1)
    package_spec_v2 = importlib.util.find_spec(package_name_v2)
    if not package_spec_v1 and not package_spec_v2:
        raise BuildDependencyError(
            "foundrytools-cli is not found. Please run `pip install foundrytools-cli`"
        )

    try:
        installed_package = importlib.import_module(
            package_name_v2 if package_spec_v2 else package_name_v1
        )
        version = getattr(installed_package, "__version__", None)
        try:
            major_version = int(version.split(".", 1)[0]) if version else None
        except (TypeError, ValueError):
            major_version = None
        if major_version is not None and major_version < 2:
            raise BuildDependencyError(
                f"foundrytools-cli version {version} is too old. Please run `pip install --upgrade foundrytools-cli`"
            )
    except Exception as error:
        if isinstance(error, BuildDependencyError):
            raise
        raise BuildDependencyError(
            f"Error checking foundrytools-cli version: {error}"
        ) from error

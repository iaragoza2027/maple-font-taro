from __future__ import annotations


class BuildDependencyError(RuntimeError):
    """Raised when a required local build dependency is unavailable."""

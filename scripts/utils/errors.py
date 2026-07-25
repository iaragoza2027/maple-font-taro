from __future__ import annotations


class BuildDependencyError(RuntimeError):
    """Raised when a required local build dependency is unavailable."""


class CJKSourceUnavailable(BuildDependencyError):
    """Raised when an explicitly requested CJK source cannot be resolved."""


class CJKBaseUnavailable(BuildDependencyError):
    """Raised when no valid CJK static or variable base can be resolved."""

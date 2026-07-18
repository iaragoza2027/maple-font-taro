from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


UnicodeRange = tuple[int, int]


def parse_unicode_range(value: str) -> UnicodeRange:
    raw = value.lower().removeprefix("u+")
    start, separator, end = raw.partition("-")
    first = int(start, 16)
    return first, int(end, 16) if separator else first


@dataclass(frozen=True, slots=True)
class FontSource:
    path: Path
    enable: bool = True
    unicode_ranges: tuple[UnicodeRange, ...] = ()
    width_scale: float | None = None
    axes: dict[str, float] | None = None

    @classmethod
    def parse(cls, value: str | dict[str, Any]) -> FontSource:
        if isinstance(value, str):
            return cls(path=Path(value))
        if not isinstance(value, dict) or not value.get("path"):
            raise ValueError("Font source must define a path")
        width_scale = float(value["width_scale"]) if "width_scale" in value else None
        if width_scale is not None and width_scale <= 0:
            raise ValueError(f"width_scale must be > 0, got {width_scale}")
        return cls(
            path=Path(value["path"]),
            enable=bool(value.get("enable", True)),
            unicode_ranges=tuple(
                parse_unicode_range(item) for item in value.get("unicode_range", ())
            ),
            width_scale=width_scale,
            axes={str(key): float(axis) for key, axis in value.get("axes", {}).items()}
            or None,
        )


@dataclass(frozen=True, slots=True)
class PreparedSource:
    path: Path
    is_temp: bool = False
    unicode_ranges: tuple[UnicodeRange, ...] = ()
    width_scale: float | None = None


@dataclass(frozen=True, slots=True)
class MergeConfig:
    family_name: str
    output_dir: Path
    instances: dict[str, tuple[FontSource, ...]]
    line_height: float | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> MergeConfig:
        for field in ("family_name", "output_dir", "instances"):
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        raw_instances = data["instances"]
        if not isinstance(raw_instances, dict) or not raw_instances:
            raise ValueError("'instances' must be a non-empty object")
        return cls(
            family_name=str(data["family_name"]),
            output_dir=Path(data["output_dir"]),
            instances={
                str(style): tuple(FontSource.parse(source) for source in sources)
                for style, sources in raw_instances.items()
            },
            line_height=(
                float(data["line_height"])
                if data.get("line_height") is not None
                else None
            ),
        )

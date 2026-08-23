from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fontTools.subset import Options, Subsetter

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scripts.font_ops.fonttools import TTFont


@dataclass(frozen=True, slots=True)
class SubsetConfig:
    """Explicit FontTools subset settings; omitted fields keep its defaults."""

    hinting: bool | None = None
    layout_features: tuple[str, ...] | None = None
    name_ids: tuple[int | str, ...] | None = None
    name_legacy: bool | None = None
    name_languages: tuple[int | str, ...] | None = None
    notdef_outline: bool | None = None
    recalc_bounds: bool | None = None
    recalc_timestamp: bool | None = None
    recommended_glyphs: bool | None = None


def subset_to_codepoints(
    font: TTFont,
    codepoints: Iterable[int],
    options: SubsetConfig | None = None,
) -> TTFont:
    """Keep only glyphs reachable from the requested Unicode codepoints."""
    return _subset(font, options=options, unicodes=codepoints)


def subset_to_glyphs(
    font: TTFont,
    glyph_names: Iterable[str],
    options: SubsetConfig | None = None,
) -> TTFont:
    """Keep only the requested glyph names and their dependencies."""
    return _subset(font, options=options, glyphs=glyph_names)


def _subset(
    font: TTFont,
    *,
    options: SubsetConfig | None,
    unicodes: Iterable[int] | None = None,
    glyphs: Iterable[str] | None = None,
) -> TTFont:
    if (unicodes is None) == (glyphs is None):
        raise ValueError("Provide exactly one subset target")

    subsetter = (
        Subsetter(options=_fonttools_options(options))
        if options is not None
        else Subsetter()
    )
    if unicodes is not None:
        subsetter.populate(unicodes=unicodes)
    else:
        subsetter.populate(glyphs=glyphs)
    subsetter.subset(font)
    return font


def _fonttools_options(config: SubsetConfig) -> Options:
    settings: dict[str, object] = {}
    if config.hinting is not None:
        settings["hinting"] = config.hinting
    if config.layout_features is not None:
        settings["layout_features"] = list(config.layout_features)
    if config.name_ids is not None:
        settings["name_IDs"] = list(config.name_ids)
    if config.name_legacy is not None:
        settings["name_legacy"] = config.name_legacy
    if config.name_languages is not None:
        settings["name_languages"] = list(config.name_languages)
    if config.notdef_outline is not None:
        settings["notdef_outline"] = config.notdef_outline
    if config.recalc_bounds is not None:
        settings["recalc_bounds"] = config.recalc_bounds
    if config.recalc_timestamp is not None:
        settings["recalc_timestamp"] = config.recalc_timestamp
    if config.recommended_glyphs is not None:
        settings["recommended_glyphs"] = config.recommended_glyphs
    return Options(**settings)


__all__ = ["SubsetConfig", "subset_to_codepoints", "subset_to_glyphs"]

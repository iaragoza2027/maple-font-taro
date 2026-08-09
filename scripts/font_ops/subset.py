from __future__ import annotations

from typing import TYPE_CHECKING

from fontTools.subset import Subsetter

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scripts.font_ops.fonttools import SubsetOptions, TTFont


def subset_to_codepoints(
    font: TTFont,
    codepoints: Iterable[int],
    options: SubsetOptions | None = None,
) -> TTFont:
    """Keep only glyphs reachable from the requested Unicode codepoints."""
    return _subset(font, options=options, unicodes=codepoints)


def subset_to_glyphs(
    font: TTFont,
    glyph_names: Iterable[str],
    options: SubsetOptions | None = None,
) -> TTFont:
    """Keep only the requested glyph names and their dependencies."""
    return _subset(font, options=options, glyphs=glyph_names)


def _subset(
    font: TTFont,
    *,
    options: SubsetOptions | None,
    unicodes: Iterable[int] | None = None,
    glyphs: Iterable[str] | None = None,
) -> TTFont:
    if (unicodes is None) == (glyphs is None):
        raise ValueError("Provide exactly one subset target")

    subsetter = Subsetter(options=options) if options is not None else Subsetter()
    if unicodes is not None:
        subsetter.populate(unicodes=unicodes)
    else:
        subsetter.populate(glyphs=glyphs)
    subsetter.subset(font)
    return font


__all__ = ["subset_to_codepoints", "subset_to_glyphs"]

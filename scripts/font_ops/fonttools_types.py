"""Local protocols for FontTools tables whose generated stubs omit fields."""

from __future__ import annotations

from typing import Any, Protocol


class PanoseTable(Protocol):
    bFamilyType: int
    bProportion: int
    bSpacing: int


class OS2Table(Protocol):
    fsSelection: int
    panose: PanoseTable
    sCapHeight: int
    sTypoAscender: int
    sTypoDescender: int
    sxHeight: int
    usWeightClass: int
    usWinAscent: int
    usWinDescent: int
    ulCodePageRange1: int
    version: int
    xAvgCharWidth: int

    def recalcAvgCharWidth(self, ttFont: Any) -> None: ...

    def recalcUnicodeRanges(self, ttFont: Any) -> None: ...


class HeadTable(Protocol):
    flags: int
    macStyle: int
    unitsPerEm: int
    yMax: int
    yMin: int


class HheaTable(Protocol):
    advanceWidthMax: int
    ascent: int
    caretSlopeRise: int
    caretSlopeRun: int
    descent: int
    numberOfHMetrics: int

    def recalc(self, ttFont: Any) -> None: ...


class PostTable(Protocol):
    isFixedPitch: bool
    italicAngle: float


class GlyfTable(Protocol):
    glyphs: dict[str, Any]

    def setGlyphOrder(self, glyph_order: list[str]) -> None: ...


class CFFTable(Protocol):
    cff: Any


class GaspTable(Protocol):
    gaspRange: dict[int, int]


class MetricsTable(Protocol):
    metrics: dict[str, tuple[int, int]]


class SubsetOptions(Protocol):
    layout_features: list[str]
    name_IDs: list[int | str]
    name_legacy: bool
    name_languages: list[int | str]
    notdef_outline: bool
    recalc_bounds: bool
    recalc_timestamp: bool
    recommended_glyphs: bool

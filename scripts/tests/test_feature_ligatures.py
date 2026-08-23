from __future__ import annotations

import re
import unittest
from io import BytesIO

import uharfbuzz as hb
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from scripts.feature import ast
from scripts.feature.calt import equal_arrow, hyphen_arrow
from scripts.feature.calt._infinite_utils import InfiniteOptions
from scripts.feature.cv import cv01
from scripts.feature.ss import ss08


class InfiniteLigaturePriorityTest(unittest.TestCase):
    static_cases = (
        ("<=>", "less_equal_greater.liga"),
        ("<==>", "less_equal_equal_greater.liga"),
        ("<==", "less_equal_equal.liga"),
        ("==>", "equal_equal_greater.liga"),
        ("=>", "equal_greater.liga"),
        ("<=|", "less_equal_bar.liga"),
        ("|=>", "bar_equal_greater.liga"),
        ("<=", "less_equal.liga"),
        ("=>=", "equal_greater_equal.liga"),
        ("<->", "less_hyphen_greater.liga"),
        ("->", "hyphen_greater.liga"),
        ("<-", "less_hyphen.liga"),
        ("-->", "hyphen_hyphen_greater.liga"),
        ("<--", "less_hyphen_hyphen.liga"),
        ("<-<", "less_hyphen_less.liga"),
        (">->", "greater_hyphen_greater.liga"),
        ("<-|", "less_hyphen_bar.liga"),
        ("|->", "bar_hyphen_greater.liga"),
    )
    punctuation_cases = (
        ("(<=>)", "less_equal_greater.liga"),
        ("[<==>]", "less_equal_equal_greater.liga"),
        ("{=>=}", "equal_greater_equal.liga"),
        ("|<=>|", "less_equal_greater.liga"),
        ("(<->)", "less_hyphen_greater.liga"),
        ("[-->]", "hyphen_hyphen_greater.liga"),
        ("{|->}", "bar_hyphen_greater.liga"),
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.font = hb.Font(hb.Face(cls._build_font_data()))

    @staticmethod
    def _build_font_data() -> bytes:
        cls_var = ast.Clazz("Var", ["A"])
        lookups = [
            *equal_arrow.get_lookup(cls_var, InfiniteOptions(enabled=True)),
            *hyphen_arrow.get_lookup(cls_var, InfiniteOptions(enabled=True)),
        ]
        source = ast.create(
            [
                ast.Clazz("Question", ["question"]),
                ast.Clazz("Digit", ["zero"]),
                cls_var,
                ast.Feature("calt", lookups, "test"),
                cv01.cv01_feat(InfiniteOptions(enabled=True)),
                ss08.ss08_feat,
            ]
        )
        character_map = {
            ord("<"): "less",
            ord("="): "equal",
            ord(">"): "greater",
            ord("-"): "hyphen",
            ord("|"): "bar",
            ord("("): "parenleft",
            ord(")"): "parenright",
            ord("["): "bracketleft",
            ord("]"): "bracketright",
            ord("{"): "braceleft",
            ord("}"): "braceright",
            ord("?"): "question",
            ord("!"): "exclam",
            ord("/"): "slash",
            ord("+"): "plus",
            ord("#"): "numbersign",
        }
        glyph_order = [
            ".notdef",
            *sorted(
                set(re.findall(r"\b[A-Za-z][A-Za-z0-9_.]*\b", source))
                | set(character_map.values())
            ),
        ]
        builder = FontBuilder(1000, isTTF=True)
        builder.setupGlyphOrder(glyph_order)
        builder.setupCharacterMap(character_map)
        builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in glyph_order})
        builder.setupHorizontalMetrics(dict.fromkeys(glyph_order, (600, 0)))
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupNameTable({"familyName": "Feature Test", "styleName": "Regular"})
        builder.setupOS2()
        builder.setupPost()
        addOpenTypeFeaturesFromString(builder.font, source)

        buffer = BytesIO()
        builder.font.save(buffer)
        return buffer.getvalue()

    def _shape(self, text: str, features: dict[str, bool] | None = None) -> list[str]:
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(self.font, buffer, {"calt": True, **(features or {})})
        return [self.font.get_glyph_name(info.codepoint) for info in buffer.glyph_infos]

    def test_static_arrow_ligatures_win_before_dynamic_expansion(self) -> None:
        for text, static_glyph in self.static_cases:
            with self.subTest(text=text):
                glyph_names = self._shape(text)

                self.assertIn(static_glyph, glyph_names)
                self.assertFalse(any(name.endswith(".seq") for name in glyph_names))

    def test_static_arrow_ligatures_survive_neutral_punctuation(self) -> None:
        for text, static_glyph in self.punctuation_cases:
            with self.subTest(text=text):
                glyph_names = self._shape(text)

                self.assertIn(static_glyph, glyph_names)
                self.assertFalse(any(name.endswith(".seq") for name in glyph_names))

    def test_dynamic_expansion_shapes_arrow_sequences_without_static_ligatures(
        self,
    ) -> None:
        cases = {
            "<===>": [
                "less_equal.sta.seq",
                "equal.mid.seq",
                "equal.mid.seq",
                "equal.mid.seq",
                "greater_equal.end.seq",
            ],
            "<--->": [
                "less_hyphen.sta.seq",
                "hyphen.mid.seq",
                "hyphen.mid.seq",
                "hyphen.mid.seq",
                "greater_hyphen.end.seq",
            ],
        }

        for text, expected_glyphs in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self._shape(text), expected_glyphs)

    def test_conflicting_neighbor_symbols_prefer_dynamic_expansion(self) -> None:
        cases = {
            "<=>=": [
                "less_equal.sta.seq",
                "equal.mid.seq",
                "greater_equal.mid.seq",
                "equal.end.seq",
            ],
            "===>": [
                "equal.sta.seq",
                "equal.mid.seq",
                "equal.mid.seq",
                "greater_equal.end.seq",
            ],
            "<-->": [
                "less_hyphen.sta.seq",
                "hyphen.mid.seq",
                "hyphen.mid.seq",
                "greater_hyphen.end.seq",
            ],
            "-->-": [
                "hyphen.sta.seq",
                "hyphen.mid.seq",
                "greater_hyphen.mid.seq",
                "hyphen.end.seq",
            ],
            "->>": ["hyphen.sta.seq", "greater_hyphen.end.seq", "greater"],
        }

        for text, expected_glyphs in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self._shape(text), expected_glyphs)

    def test_contextual_punctuation_blocks_conflicting_arrow_ligatures(self) -> None:
        cases = {
            "(?<=>": ["parenleft", "question", "less", "equal", "greater"],
            "+->": ["plus", "hyphen.sta.seq", "greater_hyphen.end.seq"],
            "<-/": ["less", "hyphen", "slash"],
        }

        for text, expected_glyphs in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self._shape(text), expected_glyphs)

    def test_cv01_and_ss08_preserve_arrow_ligature_priorities(self) -> None:
        features = {"cv01": True, "ss08": True}
        cases = {
            "=>": ["SPC", "equal_greater.liga.cv01"],
            "<===>": [
                "less_equal.sta.seq.cv01",
                "equal.mid.seq",
                "equal.mid.seq",
                "equal.mid.seq",
                "greater_equal.end.seq.cv01",
            ],
            "-<<": ["SPC", "SPC", "hyphen_less_less.liga.ss08"],
            "->>": ["hyphen.sta.seq", "greater_hyphen.end.seq.cv01", "greater"],
        }

        for text, expected_glyphs in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self._shape(text, features), expected_glyphs)

from dataclasses import dataclass
from typing import TypeVar

import scripts.feature.ast as ast

_T = TypeVar("_T")


@dataclass(frozen=True)
class InfiniteOptions:
    enabled: bool = True

    def ignore_when_enabled(self, *items: _T) -> list[_T]:
        if self.enabled:
            return []
        return list(items)

    def ignore_when_disabled(self, *items: _T) -> list[_T]:
        if not self.enabled:
            return []
        return list(items)


def infinite_rules(
    glyph: str,
    cls_start: ast.Clazz,
    symbols: list[str],
    extra_rules: list[ast.Line] | None = None,
):
    if extra_rules is None:
        extra_rules = []
    prefix = []

    for s in symbols:
        prefix.append(ast.gly_seq(s + glyph, "sta"))
        prefix.append(ast.gly_seq(s + glyph, "mid"))

    prefix_cls = ast.cls(prefix, cls_start)

    return [
        ast.subst(
            prefix_cls, glyph, ast.cls(symbols, glyph), ast.gly_seq(glyph, "mid")
        ),
        ast.subst(prefix_cls, glyph, None, ast.gly_seq(glyph, "end")),
        *[
            [
                ast.subst(cls_start, s, glyph, ast.gly_seq(s + glyph, "mid")),
                ast.subst(cls_start, s, None, ast.gly_seq(s + glyph, "end")),
                ast.subst(None, s, glyph, ast.gly_seq(s + glyph, "sta")),
            ]
            for s in symbols
        ],
        *extra_rules,
        # Must be end of rules
        ast.subst(None, glyph, ast.cls(symbols, glyph), ast.gly_seq(glyph, "sta")),
    ]

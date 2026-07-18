import scripts.feature.ast as ast
from typing import TypeVar


_T = TypeVar("_T")


class InfiniteHelper:
    __USE_INFINITE_ARROW: bool

    def __init__(self) -> None:
        self.__USE_INFINITE_ARROW = True

    def get(self) -> bool:
        return self.__USE_INFINITE_ARROW

    def set(self, val: bool) -> None:
        self.__USE_INFINITE_ARROW = val

    def ignore_when_enabled(self, *items: _T) -> list[_T]:
        if self.get():
            return []
        return list(items)

    def ignore_when_disabled(self, *items: _T) -> list[_T]:
        if not self.get():
            return []
        return list(items)


infinite_helper = InfiniteHelper()


def infinite_rules(
    glyph: str,
    cls_start: ast.Clazz,
    symbols: list[str],
    extra_rules: list[ast.Line] = [],
):
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

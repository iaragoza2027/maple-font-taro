import scripts.feature.ast as ast
from scripts.feature.base.locl import lookup_CY_BGR, lookup_CY_BGR_ITALIC


def ss12_feat(italic: bool):
    lookup = lookup_CY_BGR_ITALIC if italic else lookup_CY_BGR
    return ast.StylisticSet(
        id=12,
        desc="Bulgarian Cyrillic forms",
        content=lookup.use(),
        version="8.0",
        example="ДЛФ",
    )

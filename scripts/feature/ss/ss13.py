import scripts.feature.ast as ast
from scripts.feature.base.locl import lookup_CY_SRB, lookup_CY_SRB_ITALIC


def ss13_feat(italic: bool):
    lookup = lookup_CY_SRB_ITALIC if italic else lookup_CY_SRB
    return ast.StylisticSet(
        id=13,
        desc="Serbian Cyrillic forms",
        content=lookup.use(),
        version="8.0",
        example="б",
    )

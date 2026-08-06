import scripts.feature.ast as ast


def cv68_subst():
    return ast.subst_map(["==="], target_suffix=".cv68")


cv68_name = "Alternative `===` with 2 bars"
cv68_feat = ast.CharacterVariant(
    id=68, desc=cv68_name, content=cv68_subst(), version="8.0", example="==="
)

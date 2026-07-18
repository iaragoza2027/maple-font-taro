import scripts.feature.ast as ast


def cv11_subst():
    return ast.subst_map(["f"], target_suffix=".cv11")


cv11_name = "Alternative `f` with bottom bar, no effect in italic style"
cv11_feat_regular = ast.CharacterVariant(
    id=11, desc=cv11_name, content=cv11_subst(), version="7.7", example="f"
)

import scripts.feature.ast as ast
from scripts.feature.base.locl import lookup_TW


def cv99_subst():
    return [lookup_TW.use()]


cv99_name = "Traditional centered punctuations"
cv99_feat_cn = ast.CharacterVariant(
    id=99, desc=cv99_name, content=cv99_subst(), version="7.0", example="，。"
)

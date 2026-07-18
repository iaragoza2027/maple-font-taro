import scripts.feature.ast as ast
from scripts.feature.cv._common import GLYPHS_U


def cv45_subst():
    return ast.subst_map(GLYPHS_U, target_suffix=".cv45")


cv45_name = "Alternative italic `u` without tail"
cv45_feat_italic = ast.CharacterVariant(
    id=45, desc=cv45_name, content=cv45_subst(), version="8.0", example="u"
)

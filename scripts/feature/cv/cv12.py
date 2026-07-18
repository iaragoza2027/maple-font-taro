import scripts.feature.ast as ast
from scripts.feature.cv._common import GLYPHS_U


def cv12_subst():
    return ast.subst_map(GLYPHS_U, target_suffix=".cv12")


cv12_name = "Alternative `u` without tail, no effect in italic style"
cv12_feat_regular = ast.CharacterVariant(
    id=12, desc=cv12_name, content=cv12_subst(), version="8.0", example="u"
)

import scripts.feature.ast as ast


def cv66_subst():
    return [
        ast.subst_map(
            ["||>", "<||", "<|", "|>", "<|>", "|||>", "<|||"],
            target_suffix=".cv66",
        ),
    ]


cv66_name = "Alternative pipe arrows"
cv66_feat = ast.CharacterVariant(
    id=66, desc=cv66_name, content=cv66_subst(), version="7.8", example="|>"
)

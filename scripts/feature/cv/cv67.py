import scripts.feature.ast as ast


def cv67_subst():
    return [
        ast.subst_map(
            [
                "bar",
                "bar_bar.liga",
                "bar_bar_bar.liga",
                "underscore_bar_underscore.liga",
                "hyphen_bar.liga",
                "bar_hyphen.liga",
                "bar_bar_hyphen.liga",
                "bar_equal.liga",
                "bar_equal.sta.seq",
                "bar_equal.mid.seq",
                "bar_equal.end.seq",
                "bar_hyphen.mid.seq",
                "bar_hyphen.sta.seq",
                "bar_hyphen.end.seq",
                "bar_lines.decorator",
            ],
            target_suffix=".cv67",
        ),
    ]


cv67_name = "Alternative longer bar"
cv67_feat = ast.CharacterVariant(
    id=67, desc=cv67_name, content=cv67_subst(), version="8.0", example="|"
)

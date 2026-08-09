import scripts.feature.ast as ast
from scripts.feature.calt._infinite_utils import InfiniteOptions

_DEFAULT_INFINITE_OPTIONS = InfiniteOptions()

sfx = ".cv01"


def cv01_subst(options: InfiniteOptions):
    return [
        ast.subst_map(
            "$",
            target_suffix=sfx,
        ),
        ast.subst_map(
            "%",
            target_suffix=sfx,
        ),
        ast.subst_map(
            ["&", "&&", "&&&"],
            target_suffix=sfx,
        ),
        ast.subst_map(
            ["@", "~@"],
            target_suffix=sfx,
        ),
        ast.subst_map(
            ["Q", "Q.bg"],
            target_suffix=sfx,
        ),
        ast.subst_map(
            [
                "<=<",
                ">=>",
                "<!--",
                "<#--",
                "xml_empty_comment.liga",  # <!---->
                *options.ignore_when_enabled(
                    "=>",
                    "<==",
                    "==>",
                    "<=>",
                    "<==>",
                    "<=|",
                    "|=>",
                    "<-|",
                    "|->",
                    "<-",
                    "->",
                    "<--",
                    "-->",
                    "<-<",
                    ">->",
                    "<->",
                ),
                *options.ignore_when_disabled(
                    ast.gly_seq("<=", "sta"),
                    ast.gly_seq(">=", "end"),
                    ast.gly_seq("<-", "sta"),
                    ast.gly_seq(">-", "end"),
                ),
            ],
            target_suffix=sfx,
        ),
    ]


def cv01_feat(options: InfiniteOptions = _DEFAULT_INFINITE_OPTIONS):
    cv01_desc = "Normalize special symbols (`@ $ & % Q => ->`)"
    return ast.CharacterVariant(
        id=1, desc=cv01_desc, content=cv01_subst(options), version="7.0", example="@$&"
    )

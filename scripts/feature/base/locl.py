import scripts.feature.ast as ast

i_acc = ast.__subst("i", "idotaccent")
locl_0 = ast.Lookup(
    "locl_latn_0",
    None,
    [
        ast.script("latn"),
        ast.lang("AZE"),
        i_acc,
        ast.lang("CRT"),
        i_acc,
        ast.lang("KAZ"),
        i_acc,
        ast.lang("TAT"),
        i_acc,
        ast.lang("TRK"),
        i_acc,
    ],
)

st_acc = ast.subst_map(
    ["S", "s", "T", "t"], source_suffix="cedilla", target_suffix="commaaccent"
)

locl_LATN = ast.Lookup(
    "locl_latn_1",
    None,
    [
        ast.script("latn"),
        ast.lang("ROM"),
        st_acc,
        ast.lang("MOL"),
        st_acc,
    ],
)

glyph_2 = "periodcentered"

locl_CAT = ast.Lookup(
    "locl_latn_2",
    None,
    [
        ast.script("latn"),
        ast.lang("CAT"),
        ast.subst(["l"], glyph_2, ["l"], f"{glyph_2}.loclCAT"),
        ast.subst(["L"], glyph_2, ["L"], f"{glyph_2}.loclCAT.case"),
    ],
)

locl_NLD = ast.Lookup(
    "locl_latn_3",
    None,
    [
        ast.script("latn"),
        ast.lang("NLD"),
        ast.__subst("ij acutecomb", "ij_acute"),
        ast.__subst("IJ acutecomb", "IJ_acute"),
    ],
)

lookup_CY_BGR = ast.Lookup(
    "CyrillicBGR",
    None,
    ast.subst_map(
        [
            "De-cy",
            "El-cy",
            "Ef-cy",
            "ve-cy",
            "ge-cy",
            "de-cy",
            "zhe-cy",
            "ze-cy",
            "ii-cy",
            "iishort-cy",
            "igravecyr",
            "ka-cy",
            "el-cy",
            "pe-cy",
            "te-cy",
            "tse-cy",
            "sha-cy",
            "shcha-cy",
            "softsign-cy",
            "hardsign-cy",
            "iu-cy",
        ],
        target_suffix=".loclBGR",
    ),
)

lookup_CY_BGR_ITALIC = ast.Lookup(
    "CyrillicBGR",
    None,
    ast.subst_map(
        [
            "De-cy",
            "El-cy",
            "Ef-cy",
            "de-cy",
            "zhe-cy",
            "ze-cy",
            "ii-cy",
            "ka-cy",
            "te-cy",
            "iu-cy",
        ],
        target_suffix=".loclBGR",
    ),
)

lookup_CY_SRB = ast.Lookup(
    "CyrillicSRB",
    None,
    ast.subst_map(["be-cy"], target_suffix=".loclSRB"),
)

lookup_CY_SRB_ITALIC = ast.Lookup(
    "CyrillicSRB",
    None,
    ast.subst_map(
        ["be-cy", "de-cy", "ge-cy", "pe-cy", "te-cy"], target_suffix=".loclSRB"
    ),
)


# Must before all features
lookup_TW = ast.Lookup(
    "PunctuationTW",
    "Centered punctuations",
    ast.subst_map(
        [
            "uni3001",
            "uni3002",
            "uniFF01",
            "uniFF0C",
            "uniFF1A",
            "uniFF1B",
            "uniFF1F",
        ],
        target_suffix=".tw",
    ),
)


__locl_cn_only = [
    ast.lang("ZHH"),
    lookup_TW.use(),
    ast.lang("ZHT"),
    lookup_TW.use(),
]


def get_locl_feature_list(cn: bool, cn_only: bool = False, italic: bool = False):
    lookup_bgr = lookup_CY_BGR_ITALIC if italic else lookup_CY_BGR
    lookup_srb = lookup_CY_SRB_ITALIC if italic else lookup_CY_SRB
    locl = [
        locl_0,
        locl_LATN,
        locl_CAT,
        locl_NLD,
        ast.script("cyrl"),
        ast.lang("BGR"),
        lookup_bgr.use(),
        ast.lang("SRB"),
        lookup_srb.use(),
    ]

    if not cn:
        return [lookup_bgr, lookup_srb, ast.Feature("locl", locl, "7.0")]

    content = __locl_cn_only if cn_only else locl + __locl_cn_only
    return [
        *([] if cn_only else [lookup_bgr, lookup_srb]),
        lookup_TW,
        ast.Feature("locl", content, "7.0"),
        ast.Feature("cpct", lookup_TW.use(), "8.0"),
    ]

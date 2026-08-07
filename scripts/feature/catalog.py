from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.feature.cv import cv96, cv97, cv98, cv99

if TYPE_CHECKING:
    from scripts.feature import ast

NORMAL_ENABLED_FEATURES = (
    "cv01",
    "cv02",
    "cv33",
    "cv34",
    "cv35",
    "cv36",
    "cv61",
    "cv62",
    "ss05",
    "ss06",
    "ss07",
    "ss08",
)

CJK_FEATURES: tuple[ast.FeatureWithDocs, ...] = (
    cv96.cv96_feat_cn,
    cv97.cv97_feat_cn,
    cv98.cv98_feat_cn,
    cv99.cv99_feat_cn,
)

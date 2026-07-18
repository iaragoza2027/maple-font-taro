from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scripts.feature import ast
from scripts.feature.cv import cv96, cv97, cv98, cv99
from scripts.feature.italic import cv_list_italic, ss_list_italic
from scripts.feature.regular import cv_list_regular, ss_list_regular


FeatureStyle = Literal["regular", "italic", "cjk"]


@dataclass(frozen=True, slots=True)
class FeatureCatalogEntry:
    """A stable feature definition and the styles where it applies."""

    feature: ast.FeatureWithDocs
    styles: frozenset[FeatureStyle]

    @property
    def tag(self) -> str:
        return self.feature.tag


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


def ordered_feature_catalog() -> tuple[FeatureCatalogEntry, ...]:
    """Return the deterministic catalog used by metadata and exporters."""
    result: list[FeatureCatalogEntry] = []
    for feature in cv_list_regular() + ss_list_regular():
        result.append(FeatureCatalogEntry(feature, frozenset({"regular"})))
    for feature in cv_list_italic() + ss_list_italic():
        result.append(FeatureCatalogEntry(feature, frozenset({"italic"})))
    for feature in CJK_FEATURES:
        result.append(FeatureCatalogEntry(feature, frozenset({"cjk"})))
    return tuple(result)

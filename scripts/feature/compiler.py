import json
import re
from copy import deepcopy
from html import escape
from typing import cast

from scripts.feature import ast
from scripts.feature.base import get_base_feature_cn_only, get_base_features
from scripts.feature.base.lang import get_lang_list
from scripts.feature.calt import get_calt, get_calt_lookup
from scripts.feature.calt._infinite_utils import InfiniteOptions
from scripts.feature.catalog import CJK_FEATURES, NORMAL_ENABLED_FEATURES
from scripts.feature.italic import (
    class_list_italic,
    cv_list_italic,
    ss_list_italic,
)
from scripts.feature.regular import (
    class_list_regular,
    cls_hex_letter,
    cls_var,
    cv_list_regular,
    ss_list_regular,
)
from scripts.utils.logging import logger

normal_enabled_features = list(NORMAL_ENABLED_FEATURES)
cv_list_cn = list(CJK_FEATURES)


def generate_fea_string(
    is_italic: bool,
    is_cn: bool,
    is_normal: bool = False,
    is_calt: bool = True,
    enable_infinite: bool = True,
    enable_tag: bool = True,
    remove_italic_calt: bool = False,
):
    """
    Generates feature string.

    Args:
        is_italic (bool): Whether to generate italic features
        is_cn (bool): Whether to include Chinese-specific features
        is_normal (bool): Whether to generate normal preset
        is_calt (bool): Whether to enable calt
        infinite (bool): Whether to add infinite arrow ligatures
    """
    logger.debug(
        "Generate feature string: italic=%s, cn=%s, normal=%s, calt=%s, infinite=%s, tag=%s, remove_italic_calt=%s",
        is_italic,
        is_cn,
        is_normal,
        is_calt,
        enable_infinite,
        enable_tag,
        remove_italic_calt,
    )
    class_list = class_list_italic if is_italic else class_list_regular
    infinite_options = InfiniteOptions(enable_infinite)
    cv_list = (
        cv_list_italic(True, infinite_options)
        if is_italic
        else cv_list_regular(True, infinite_options)
    )
    ss_list = ss_list_italic(True) if is_italic else ss_list_regular(True)

    if class_list[-2].name != "Var" or class_list[-1].name != "HexLetter":
        raise TypeError("Invalid class_list, must ends with [@Var, @HexLetter]")

    calt_feat = get_calt(
        cls_var=class_list[-2],
        cls_hex_letter=class_list[-1],
        is_italic=is_italic,
        is_normal=is_normal,
        enable_tag=enable_tag,
        remove_italic_calt=remove_italic_calt,
        infinite_options=infinite_options,
    )

    # clear calt for no ligature
    if not is_calt:
        calt_feat.content = []

    cv_ss_list = deepcopy(cv_list + (cv_list_cn if is_cn else []) + ss_list)

    # Add placeholder to calt if empty, to prevent fonttools warning
    if not calt_feat.content:
        calt_feat.content = cast(
            "list[ast.Lookup | ast.Clazz | ast.Line]", ast.EMPTY_FEAT_CONTENT
        )

    return ast.create(
        [
            class_list,
            get_lang_list(),
            get_base_features(calt_feat, is_cn=is_cn, is_italic=is_italic),
            cv_ss_list,
        ],
    )


def generate_fea_string_cn_only():
    logger.debug("Generate feature string: cn_only=True")
    return ast.create(
        [
            get_base_feature_cn_only(),
            cv_list_cn,
        ],
    )


def get_all_calt_text():
    result: list[str] = []

    for item in ast.recursive_iterate(
        get_calt_lookup(
            cls_var,
            cls_hex_letter,
            True,
            infinite_options=InfiniteOptions(enabled=True),
        )
    ):
        if isinstance(item, ast.Lookup) and item.desc:
            if item.name == "escape":
                result.append(item.desc.replace("\\ ", "\\\\ "))
            elif item.name.startswith("infinite"):
                result.extend(item.desc.split(" "))
            elif not item.name.endswith("__"):
                result.append(item.desc)

    # Split into three columns
    third = (len(result) + 2) // 3  # Round up for numbers not divisible by 3

    # Create HTML table with three equal columns
    html_rows = ["<table>"]

    def wrap(desc: str):
        if not desc:
            return "<td></td>"
        _desc = escape(desc)
        italic_prefix = "italic "
        if _desc.startswith(italic_prefix):
            _desc = f"<em>{_desc.replace(italic_prefix, '')}</em>"
        return f"<td><code>{_desc}</code></td>"

    for i in range(third):
        col1 = wrap(result[i])
        col2 = wrap(result[i + third] if i + third < len(result) else "")
        col3 = wrap(result[i + 2 * third] if i + 2 * third < len(result) else "")
        html_rows.append(f"<tr>{col1}{col2}{col3}</tr>")

    html_rows.append("</table>")
    return "\n".join(html_rows)


zero_desc = "Zero style variant"


def get_version_info(
    features: list[ast.FeatureWithDocs],
) -> dict[str, dict[str, str]]:
    result = {}
    for item in features:
        if item.version not in result:
            result[item.version] = {}
        result[item.version][item.tag] = item.example
    return dict(sorted(result.items()))


def get_cv_desc():
    return "\n".join(
        [cv.desc_item() for cv in cv_list_regular()] + [f"- [v7.0] zero: {zero_desc}"]
    )


def get_cv_version_info() -> dict[str, dict[str, str]]:
    return get_version_info(cv_list_regular())


italic_code_pattern = re.compile(r"`([^`]+)`")


def get_cv_italic_desc():
    return "\n".join(
        [
            italic_code_pattern.sub(r"_`\1`_", cv.desc_item())
            for cv in cv_list_italic()
            if cv.id > 30 and cv.id < 61
        ]
    )


def get_cv_italic_version_info() -> dict[str, dict[str, str]]:
    return get_version_info(
        [cv for cv in cv_list_italic() if cv.id > 30 and cv.id < 61]
    )


def get_cv_cn_desc():
    return "\n".join([cv.desc_item() for cv in cv_list_cn])


def get_cv_cn_version_info() -> dict[str, dict[str, str]]:
    return get_version_info(cv_list_cn)


def get_ss_desc():
    result = {}
    for ss in ss_list_regular() + ss_list_italic():
        if ss.id not in result:
            desc = ss.desc_item()

            if ss.id == 5:
                desc = desc.replace("`\\\\`", "`\\\\\\\\`")
            elif ss.id == 6:
                desc = italic_code_pattern.sub(r"_`\1`_", desc)

            result[ss.id] = desc

    return "\n".join(sorted(result.values()))


def get_ss_version_info() -> dict[str, dict[str, str]]:
    ss = list({s.tag: s for s in ss_list_regular() + ss_list_italic()}.values())
    return get_version_info(sorted(ss, key=lambda x: x.tag))


__total_feat_list = (
    cv_list_regular()
    + cv_list_italic()
    + cv_list_cn
    + ss_list_regular()
    + ss_list_italic()
)


def get_total_feat_dict() -> dict[str, str]:
    result = {}

    for item in __total_feat_list:
        if item.tag not in result:
            result[item.tag] = f"[v{item.version}] " + item.desc.replace("`", "'")

    result["zero"] = "[v7.0] " + zero_desc.replace("`", "'")

    return dict(sorted(result.items()))


def get_total_feat_ts() -> str:
    feat_dict = {}

    for item in __total_feat_list:
        if item.tag not in feat_dict:
            feat_dict[item.tag] = item.desc

    feat_dict["calt"] = "Default ligatures"
    feat_dict["zero"] = zero_desc

    feat_dict = dict(sorted(feat_dict.items()))

    ts_def_props = "\n"
    for key, val in feat_dict.items():
        ts_def_props += f"  /** {val} */\n  {key}: string\n"

    return f"""// Auto generated by `python task.py fea`
// @prettier-ignore
/* eslint-disable */

export interface FeatureDescription {{{ts_def_props}}}

export const featureArray = {json.dumps(list(feat_dict.keys()), indent=2)}

export const normalFeatureArray = {json.dumps(normal_enabled_features, indent=2)}
"""


def get_freeze_moving_rules() -> list[str]:
    result = set()

    for feat in __total_feat_list:
        if feat.has_lookup:
            result.add(feat.tag)

    return list(result)

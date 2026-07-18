from __future__ import annotations

from pathlib import Path

from fontTools.feaLib.builder import (
    addOpenTypeFeatures,
    addOpenTypeFeaturesFromString,
)
from fontTools.ttLib import TTFont

from scripts.config.base import ResolvedBuildConfig, normalize_feature_freeze
from scripts.feature.compiler import generate_fea_string, get_freeze_moving_rules
from scripts.in_browser import freeze_feature


def patch_font_feature(
    config: ResolvedBuildConfig,
    font: TTFont,
    issue_fea_dir: str | Path,
    is_italic: bool,
    is_cn: bool,
    is_variable: bool,
    is_hinted: bool,
    fea_path: str,
) -> None:
    if config.apply_fea_file:
        if fea_path:
            print(f"Apply feature file [{fea_path}]")
            addOpenTypeFeatures(font, fea_path)
    elif not (is_hinted and config.infinite_arrow):
        enable_infinite = (
            bool(config.infinite_arrow)
            if config.infinite_arrow is not None
            else not is_hinted
        )
        feature_source = generate_fea_string(
            is_italic=is_italic,
            is_cn=is_cn,
            is_normal=config.feature.normal,
            is_calt=config.enable_ligature,
            enable_infinite=enable_infinite,
            enable_tag=not config.remove_tag_liga,
            variable_enabled_feature_list=[
                key
                for key, value in config.feature_freeze.items()
                if value.upper().startswith("ENABLE")
            ]
            if is_variable
            else [],
            remove_italic_calt=config.feature_freeze["cv35"]
            .upper()
            .startswith("ENABLE"),
        )
        try:
            addOpenTypeFeaturesFromString(font, feature_source)
        except Exception as error:
            issue_path = Path(issue_fea_dir) / "issue.fea"
            banner = (
                "Generated feature with "
                f"italic={is_italic}, cn={is_cn}, normal={config.feature.normal}, "
                f"calt={config.enable_ligature}, variable={is_variable}"
            )
            issue_path.write_text(
                f"# {banner}\n\n{feature_source}",
                encoding="utf-8",
            )
            raise SyntaxError(
                f"Error patching fea string: {error}\n\n"
                f"See generated fea string in {issue_path}"
            ) from error
    else:
        return

    if not is_variable:
        freeze_feature(
            font,
            get_freeze_moving_rules(),
            normalize_feature_freeze(config.feature_freeze, config.enable_ligature),
        )

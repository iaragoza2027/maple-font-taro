from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from os import getenv
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from fontTools.feaLib.builder import addOpenTypeFeatures, addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont

from source.py.cjk.config import (
    CJKBuildConfig,
    config_from_data,
    serialize_cjk_build_config,
)
from source.py.feature import (
    generate_fea_string,
    get_freeze_moving_rules,
    normal_enabled_features,
)
from source.py.freeze import freeze_feature, get_freeze_config_str, is_enable
from source.py.utils import default_weight_map, joinPaths

if TYPE_CHECKING:
    from source.py.cjk.presets import CJKPresetSpec


BuiltinCJKLocaleId = Literal["cn", "jp", "tc", "kr"]
BUILTIN_CJK_LOCALES: tuple[BuiltinCJKLocaleId, ...] = ("cn", "jp", "tc", "kr")
BuildFormatId = Literal["ttf", "otf", "woff2"]
BUILD_FORMATS: tuple[BuildFormatId, ...] = ("ttf", "otf", "woff2")
CJKOutputFormat = Literal["static", "variable"]

WIDTH_MAP = {
    "default": 600,
    "narrow": 550,
    "slim": 500,
}


def default_feature_freeze() -> dict[str, str]:
    return {
        "cv01": "ignore",
        "cv02": "ignore",
        "cv03": "ignore",
        "cv04": "ignore",
        "cv05": "ignore",
        "cv06": "ignore",
        "cv07": "ignore",
        "cv08": "ignore",
        "cv09": "ignore",
        "cv10": "ignore",
        "cv11": "ignore",
        "cv12": "ignore",
        "cv31": "ignore",
        "cv32": "ignore",
        "cv33": "ignore",
        "cv34": "ignore",
        "cv35": "ignore",
        "cv36": "ignore",
        "cv37": "ignore",
        "cv38": "ignore",
        "cv39": "ignore",
        "cv40": "ignore",
        "cv41": "ignore",
        "cv42": "ignore",
        "cv43": "ignore",
        "cv44": "ignore",
        "cv45": "ignore",
        "cv61": "ignore",
        "cv62": "ignore",
        "cv63": "ignore",
        "cv64": "ignore",
        "cv65": "ignore",
        "cv66": "ignore",
        "cv67": "ignore",
        "cv96": "ignore",
        "cv97": "ignore",
        "cv98": "ignore",
        "cv99": "ignore",
        "ss01": "ignore",
        "ss02": "ignore",
        "ss03": "ignore",
        "ss04": "ignore",
        "ss05": "ignore",
        "ss06": "ignore",
        "ss07": "ignore",
        "ss08": "ignore",
        "ss09": "ignore",
        "ss10": "ignore",
        "ss11": "ignore",
        "ss12": "ignore",
        "ss13": "ignore",
        "zero": "ignore",
    }


def default_weight_mapping() -> dict[str, int]:
    return dict(default_weight_map)


def parse_scale_factor(value: Any) -> tuple[float, float]:
    if isinstance(value, tuple) and len(value) == 2:
        return float(value[0]), float(value[1])
    if isinstance(value, float):
        return value, value
    if isinstance(value, int):
        factor = float(value)
        return factor, factor
    if isinstance(value, list):
        if len(value) != 2:
            raise argparse.ArgumentTypeError(
                "Invalid scale factor format. Use <factor> or <w_factor>,<h_factor>."
            )
        return float(value[0]), float(value[1])
    if not isinstance(value, str):
        raise argparse.ArgumentTypeError(
            "Invalid scale factor format. Use <factor> or <w_factor>,<h_factor>."
        )

    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) == 1:
        factor = float(parts[0])
        return factor, factor
    if len(parts) == 2:
        return float(parts[0]), float(parts[1])
    raise argparse.ArgumentTypeError(
        "Invalid scale factor format. Use <factor> or <w_factor>,<h_factor>."
    )


def normalize_build_formats(value: Any) -> list[BuildFormatId]:
    if value is None:
        return list(BUILD_FORMATS)

    if isinstance(value, str):
        items = [item.strip().lower() for item in value.split(",")]
    else:
        items: list[str] = []
        for raw in value:
            items.extend(item.strip().lower() for item in str(raw).split(","))

    normalized: list[BuildFormatId] = []
    for item in items:
        if not item:
            continue
        if item not in BUILD_FORMATS:
            raise ValueError(f"Unsupported build format: {item}")
        build_format = item  # type: ignore[assignment]
        if build_format not in normalized:
            normalized.append(build_format)
    return normalized or list(BUILD_FORMATS)


def normalize_cjk_locale_list(value: Any) -> list[BuiltinCJKLocaleId]:
    if value is None:
        return []

    if isinstance(value, str):
        items = [item.strip().lower() for item in value.split(",")]
    else:
        items: list[str] = []
        for raw in value:
            items.extend(item.strip().lower() for item in str(raw).split(","))

    normalized: list[BuiltinCJKLocaleId] = []
    for item in items:
        if not item:
            continue
        if item not in BUILTIN_CJK_LOCALES:
            raise ValueError(f"Unsupported CJK locale: {item}")
        locale = item  # type: ignore[assignment]
        if locale not in normalized:
            normalized.append(locale)
    return normalized


@dataclass(slots=True)
class BuildCliOptions:
    dry: bool = False
    debug: bool = False
    cjk: list[BuiltinCJKLocaleId] = field(default_factory=list)
    formats: list[BuildFormatId] = field(default_factory=lambda: list(BUILD_FORMATS))


@dataclass(slots=True)
class BuildBehaviorConfig:
    archive: bool = False
    debug: bool = False
    cache: bool = False
    least_styles: bool = False
    apply_fea_file: bool = False
    cjk_output_format: CJKOutputFormat = "static"
    formats: list[BuildFormatId] = field(default_factory=lambda: list(BUILD_FORMATS))
    use_cjk_both: bool = False


@dataclass(slots=True)
class FeatureBuildConfig:
    normal: bool = False
    feat: list[str] = field(default_factory=list)
    hinted: bool = True
    liga: bool = True
    infinite_arrow: bool | None = None
    remove_tag_liga: bool = False
    line_height: float = 1.0
    width: str = "default"


@dataclass(slots=True)
class NerdFontBuildConfig:
    enable: bool = True
    version: str = "3.2.1"
    mono: bool = False
    propo: bool = False
    use_font_patcher: bool = False
    glyphs: list[str] = field(default_factory=lambda: ["--complete"])
    extra_args: list[str] = field(default_factory=list)

    def to_dict(self, *, include_enable: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_enable:
            data.pop("enable", None)
        return data


@dataclass(slots=True)
class CJKCommonBuildOptions:
    with_nerd_font: bool = True
    fix_meta_table: bool = True
    clean_cache: bool = False
    narrow: bool = False
    use_hinted: bool = False
    scale_factor: tuple[float, float] = (1.0, 1.0)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scale_factor"] = list(self.scale_factor)
        return data


@dataclass(slots=True)
class CustomCJKEntryConfig:
    enable: bool
    build_config: CJKBuildConfig

    def to_dict(self) -> dict[str, Any]:
        data = serialize_cjk_build_config(self.build_config)
        data["enable"] = self.enable
        return data


@dataclass(slots=True)
class CJKLocaleSelection:
    cn: bool = False
    jp: bool = False
    tc: bool = False
    kr: bool = False
    custom: list[CustomCJKEntryConfig] = field(default_factory=list)

    def builtin_enabled_locales(self) -> list[BuiltinCJKLocaleId]:
        return [locale for locale in BUILTIN_CJK_LOCALES if bool(getattr(self, locale))]

    def set_builtin_enabled(self, locale: BuiltinCJKLocaleId, enabled: bool) -> None:
        setattr(self, locale, enabled)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cn": self.cn,
            "jp": self.jp,
            "tc": self.tc,
            "kr": self.kr,
            "custom": [entry.to_dict() for entry in self.custom],
        }


@dataclass(slots=True)
class ResolvedCJKBuildEntry:
    entry_id: str
    locale_name: str
    build_config: CJKBuildConfig
    common_options: CJKCommonBuildOptions
    is_builtin: bool
    preset_id: BuiltinCJKLocaleId | None = None
    preset_spec: CJKPresetSpec | None = None

    @property
    def display_name(self) -> str:
        if self.preset_spec is not None:
            return self.preset_spec.family_suffix
        return self.locale_name

    @property
    def download_locale(self) -> BuiltinCJKLocaleId | None:
        return self.preset_id if self.is_builtin else None


@dataclass(slots=True)
class CJKBuildSelection:
    locales: CJKLocaleSelection = field(default_factory=CJKLocaleSelection)
    common_options: CJKCommonBuildOptions = field(default_factory=CJKCommonBuildOptions)
    entries: list[ResolvedCJKBuildEntry] = field(default_factory=list)

    def selected_entries(self) -> list[ResolvedCJKBuildEntry]:
        return list(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "locales": self.locales.to_dict(),
            **self.common_options.to_dict(),
        }


@dataclass(slots=True)
class BuildIdentityConfig:
    base_family_name: str = "Maple Mono"
    family_name: str = "Maple Mono"
    family_name_compact: str = "MapleMono"
    version_tag: str = "v7.9"
    version: str = "7.9"
    version_str: str = "Version 7.900"
    beta: str | None = None


@dataclass(slots=True)
class BuildMetricsConfig:
    weight_mapping: dict[str, int] = field(default_factory=default_weight_mapping)
    vertical_metric: tuple[int, int] = (1020, -300)
    glyph_width: int = 600
    glyph_width_cn_narrow: int = 1000
    ttfautohint_param: dict[str, Any] = field(default_factory=dict)
    pool_size: int = 1 if not getenv("CODESPACE_NAME") else 4
    github_mirror: str = "github.com"


@dataclass(slots=True)
class ResolvedBuildConfig:
    behavior: BuildBehaviorConfig = field(default_factory=BuildBehaviorConfig)
    feature: FeatureBuildConfig = field(default_factory=FeatureBuildConfig)
    nerd_font: NerdFontBuildConfig = field(default_factory=NerdFontBuildConfig)
    cjk: CJKBuildSelection = field(default_factory=CJKBuildSelection)
    identity: BuildIdentityConfig = field(default_factory=BuildIdentityConfig)
    metrics: BuildMetricsConfig = field(default_factory=BuildMetricsConfig)
    feature_freeze: dict[str, str] = field(default_factory=default_feature_freeze)

    @property
    def archive(self) -> bool:
        return self.behavior.archive

    @property
    def debug(self) -> bool:
        return self.behavior.debug

    @property
    def cache(self) -> bool:
        return self.behavior.cache

    @property
    def least_styles(self) -> bool:
        return self.behavior.least_styles

    @property
    def apply_fea_file(self) -> bool:
        return self.behavior.apply_fea_file

    @property
    def cjk_output_format(self) -> CJKOutputFormat:
        return self.behavior.cjk_output_format

    @property
    def formats(self) -> list[BuildFormatId]:
        return self.behavior.formats

    @property
    def use_cjk_both(self) -> bool:
        return self.behavior.use_cjk_both

    @property
    def use_cn_both(self) -> bool:
        return self.behavior.use_cjk_both

    @property
    def family_name(self) -> str:
        return self.identity.family_name

    @property
    def family_name_compact(self) -> str:
        return self.identity.family_name_compact

    @property
    def version(self) -> str:
        return self.identity.version

    @property
    def version_str(self) -> str:
        return self.identity.version_str

    @property
    def version_tag(self) -> str:
        return self.identity.version_tag

    @property
    def beta(self) -> str | None:
        return self.identity.beta

    @property
    def use_hinted(self) -> bool:
        return self.feature.hinted

    @property
    def enable_ligature(self) -> bool:
        return self.feature.liga

    @property
    def infinite_arrow(self) -> bool | None:
        return self.feature.infinite_arrow

    @property
    def remove_tag_liga(self) -> bool:
        return self.feature.remove_tag_liga

    @property
    def line_height(self) -> float:
        return self.feature.line_height

    @property
    def width(self) -> str:
        return self.feature.width

    @property
    def pool_size(self) -> int:
        return self.metrics.pool_size

    @property
    def weight_mapping(self) -> dict[str, int]:
        return self.metrics.weight_mapping

    @property
    def vertical_metric(self) -> tuple[int, int]:
        return self.metrics.vertical_metric

    @property
    def glyph_width(self) -> int:
        return self.metrics.glyph_width

    @property
    def glyph_width_cn_narrow(self) -> int:
        return self.metrics.glyph_width_cn_narrow

    @property
    def ttfautohint_param(self) -> dict[str, Any]:
        return self.metrics.ttfautohint_param

    @property
    def github_mirror(self) -> str:
        return self.metrics.github_mirror

    @property
    def freeze_config_str(self) -> str:
        return get_freeze_config_str(self.feature_freeze, self.enable_ligature)

    def get_target_width(self) -> int:
        return WIDTH_MAP.get(self.width, WIDTH_MAP["default"])

    def get_width_name(self) -> str | None:
        if self.width == "narrow":
            return "NR"
        if self.width == "slim":
            return "SL"
        return None

    def get_selected_cjk_entries(self) -> list[ResolvedCJKBuildEntry]:
        return self.cjk.selected_entries()

    def wants_format(self, build_format: str) -> bool:
        return build_format in self.formats

    def get_nf_suffix_compact(self) -> str:
        full = self.get_nf_suffix()
        if not full:
            return ""
        return full[1]

    def get_nf_suffix(self) -> Literal["Mono", "Propo", ""]:
        extra_args = self.nerd_font.extra_args
        if (
            self.nerd_font.mono
            or "-s" in extra_args
            or "--mono" in extra_args
            or "--single-width-glyphs" in extra_args
        ):
            return "Mono"
        if self.nerd_font.propo or "--variable-width-glyphs" in extra_args:
            return "Propo"
        return ""

    def get_valid_glyph_width_list(
        self,
        is_cjk: bool = False,
        cjk_narrow: bool = False,
    ) -> list[int]:
        result = [0]
        width_name = self.get_width_name()
        if width_name:
            width = self.get_target_width()
            result.append(width)
            if is_cjk:
                result.append(width * 2)
            return result

        result.append(self.glyph_width)
        if is_cjk:
            result.append(
                self.glyph_width_cn_narrow if cjk_narrow else 2 * self.glyph_width
            )
        return result

    def freeze_feature_static(self, font: TTFont, is_variable: bool) -> None:
        if not is_variable:
            freeze_feature(
                font=font,
                calt=self.enable_ligature,
                moving_rules=get_freeze_moving_rules(),
                config=self.feature_freeze,
            )

    def patch_font_feature(
        self,
        font: TTFont,
        issue_fea_dir: str,
        is_italic: bool,
        is_cn: bool,
        is_variable: bool,
        is_hinted: bool,
        fea_path: str,
    ) -> None:
        if self.apply_fea_file:
            if fea_path:
                print(f"Apply feature file [{fea_path}]")
                addOpenTypeFeatures(font, fea_path)
            self.freeze_feature_static(font, is_variable)
            return

        if is_hinted and self.infinite_arrow:
            return

        enable_infinite = (
            bool(self.infinite_arrow)
            if self.infinite_arrow is not None
            else not is_hinted
        )

        fea_str = generate_fea_string(
            is_italic=is_italic,
            is_cn=is_cn,
            is_normal=self.feature.normal,
            is_calt=self.enable_ligature,
            enable_infinite=enable_infinite,
            enable_tag=not self.remove_tag_liga,
            variable_enabled_feature_list=[
                key for key, val in self.feature_freeze.items() if is_enable(val)
            ]
            if is_variable
            else [],
            remove_italic_calt=is_enable(self.feature_freeze["cv35"]),
        )
        try:
            addOpenTypeFeaturesFromString(font, fea_str)
        except Exception as error:
            issue_fea_path = joinPaths(issue_fea_dir, "issue.fea")
            with open(issue_fea_path, "w+", encoding="utf-8") as file:
                banner = (
                    "Generated feature with "
                    f"italic={is_italic}, cn={is_cn}, normal={self.feature.normal}, "
                    f"calt={self.enable_ligature}, variable={is_variable}"
                )
                file.write(f"# {banner}\n\n{fea_str}")
            raise SyntaxError(
                f"Error patching fea string: {error}\n\nSee generated fea string in {issue_fea_path}"
            ) from error
        self.freeze_feature_static(font, is_variable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "behavior": asdict(self.behavior),
            "feature": {
                **asdict(self.feature),
                "feature_freeze": dict(self.feature_freeze),
                "freeze_config_str": self.freeze_config_str,
            },
            "nerd_font": self.nerd_font.to_dict(),
            "cjk": self.cjk.to_dict(),
            "identity": asdict(self.identity),
            "metrics": {
                **asdict(self.metrics),
                "vertical_metric": list(self.metrics.vertical_metric),
            },
        }

    def to_build_record(self) -> dict[str, Any]:
        return {
            "version": self.version_tag,
            "family_name": self.family_name,
            "line_height": self.line_height,
            "width": self.width,
            "use_hinted": self.use_hinted,
            "ligature": self.enable_ligature,
            "remove_tag_liga": self.remove_tag_liga,
            "infinite_arrow": "default"
            if self.infinite_arrow is None
            else self.infinite_arrow,
            "weight_mapping": dict(self.weight_mapping),
            "feature_freeze": dict(self.feature_freeze),
            "formats": list(self.formats),
            "nerd_font": self.nerd_font.to_dict(include_enable=False),
            "cjk_format": self.cjk_output_format,
            "cjk": self.cjk.to_dict(),
        }


def default_cjk_config() -> dict[str, Any]:
    return CJKBuildSelection().to_dict()


def normalize_cjk_config(
    raw_cjk: dict[str, Any] | None,
    legacy_cn: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selection = CJKBuildSelection()
    if raw_cjk and isinstance(raw_cjk, dict):
        raw_locales = raw_cjk.get("locales", {})
        if isinstance(raw_locales, dict):
            for locale in BUILTIN_CJK_LOCALES:
                selection.locales.set_builtin_enabled(
                    locale,
                    bool(raw_locales.get(locale, False)),
                )
            raw_custom = raw_locales.get("custom", [])
            if isinstance(raw_custom, list):
                for entry in raw_custom:
                    if not isinstance(entry, dict):
                        continue
                    entry_data = dict(entry)
                    enable = bool(entry_data.pop("enable", True))
                    selection.locales.custom.append(
                        CustomCJKEntryConfig(
                            enable=enable,
                            build_config=config_from_data(entry_data, Path(".")),
                        )
                    )

        for key in (
            "with_nerd_font",
            "fix_meta_table",
            "clean_cache",
            "narrow",
            "use_hinted",
        ):
            if key in raw_cjk:
                setattr(selection.common_options, key, bool(raw_cjk[key]))
        if "scale_factor" in raw_cjk:
            selection.common_options.scale_factor = parse_scale_factor(
                raw_cjk["scale_factor"]
            )

    if legacy_cn and isinstance(legacy_cn, dict):
        if legacy_cn.get("enable"):
            selection.locales.cn = True
        for key in (
            "with_nerd_font",
            "fix_meta_table",
            "clean_cache",
            "narrow",
            "use_hinted",
        ):
            if key in legacy_cn:
                setattr(selection.common_options, key, bool(legacy_cn[key]))
        if "scale_factor" in legacy_cn:
            selection.common_options.scale_factor = parse_scale_factor(
                legacy_cn["scale_factor"]
            )

    return selection.to_dict()


def serialize_cjk_config(
    cjk_config: CJKBuildSelection | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(cjk_config, CJKBuildSelection):
        return cjk_config.to_dict()
    return normalize_cjk_config(cjk_config)


__all__ = [
    "BUILD_FORMATS",
    "BUILTIN_CJK_LOCALES",
    "WIDTH_MAP",
    "BuildBehaviorConfig",
    "BuildCliOptions",
    "BuildFormatId",
    "BuildIdentityConfig",
    "BuildMetricsConfig",
    "BuiltinCJKLocaleId",
    "CJKBuildSelection",
    "CJKCommonBuildOptions",
    "CJKLocaleSelection",
    "CustomCJKEntryConfig",
    "FeatureBuildConfig",
    "NerdFontBuildConfig",
    "ResolvedBuildConfig",
    "ResolvedCJKBuildEntry",
    "default_cjk_config",
    "default_feature_freeze",
    "default_weight_mapping",
    "normalize_build_formats",
    "normalize_cjk_config",
    "normalize_cjk_locale_list",
    "parse_scale_factor",
    "serialize_cjk_config",
    "normal_enabled_features",
]

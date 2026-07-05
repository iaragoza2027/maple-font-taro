from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from os import environ, listdir, path
from pathlib import Path
from typing import Any

from source.py.build.config import (
    CJK_LOCALES,
    BuildBehaviorConfig,
    BuildIdentityConfig,
    BuildMetricsConfig,
    CJKBuildSelection,
    CJKLocaleConfig,
    FeatureBuildConfig,
    NerdFontBuildConfig,
    ResolvedBuildConfig,
    default_feature_freeze,
    default_weight_mapping,
    normalize_build_formats,
    normalize_cjk_locale_list,
    parse_scale_factor,
)
from source.py.feature import normal_enabled_features
from source.py.utils import check_font_patcher, get_font_forge_bin, joinPaths


def check_file_count(dir_path: str, min_count: int = 16, end: str | None = None) -> bool:
    if not path.isdir(dir_path):
        return False
    return len([file for file in listdir(dir_path) if end is None or file.endswith(end)]) >= min_count


@dataclass(slots=True)
class RuntimeBuildPlan:
    src_dir: str
    output_root: str
    output_otf: str
    output_ttf: str
    output_ttf_hinted: str
    output_variable: str
    output_woff2: str
    output_nf: str
    ttf_base_dir: str
    has_cache: bool
    is_nf_built: bool
    is_cjk_built: bool
    effective_github_mirror: str
    font_forge_bin: str | None

    @classmethod
    def from_config(cls, config: ResolvedBuildConfig) -> RuntimeBuildPlan:
        output_root = "fonts"
        output_ttf = joinPaths(output_root, "TTF")
        output_ttf_hinted = joinPaths(output_root, "TTF-AutoHint")
        return cls(
            src_dir="source",
            output_root=output_root,
            output_otf=joinPaths(output_root, "OTF"),
            output_ttf=output_ttf,
            output_ttf_hinted=output_ttf_hinted,
            output_variable=joinPaths(output_root, "Variable"),
            output_woff2=joinPaths(output_root, "Woff2"),
            output_nf=joinPaths(output_root, "NF"),
            ttf_base_dir=output_ttf_hinted if config.use_hinted else output_ttf,
            has_cache=(
                check_file_count(joinPaths(output_root, "Variable"), min_count=2, end=".ttf")
                and check_file_count(output_ttf, min_count=4, end=".ttf")
                and check_file_count(output_ttf_hinted, min_count=4, end=".ttf")
            ),
            is_nf_built=False,
            is_cjk_built=False,
            effective_github_mirror=environ.get("GITHUB", config.github_mirror),
            font_forge_bin=get_font_forge_bin(),
        )

    @property
    def output_dir(self) -> str:
        return self.output_root

    def feature_file_path(self, is_italic: bool, is_cjk: bool = False) -> str:
        return joinPaths(
            self.src_dir,
            "features",
            ("italic" if is_italic else "regular") + ("_cn" if is_cjk else "") + ".fea",
        )

    def get_feature_file_path(self, is_italic: bool, is_cjk: bool = False) -> str:
        return self.feature_file_path(is_italic, is_cjk)

    def resolve_font_patcher_usage(
        self, config: ResolvedBuildConfig, should_exit: bool = True
    ) -> bool:
        if not (
            config.nerd_font.extra_args
            or config.nerd_font.use_font_patcher
            or config.nerd_font.glyphs != ["--complete"]
        ):
            return False

        if (not self.font_forge_bin or not path.exists(self.font_forge_bin)) and should_exit:
            print(
                f"FontForge bin ({self.font_forge_bin}) not found, cannot build with Nerd Font Patcher"
            )
            exit(1)

        if (
            not check_font_patcher(
                version=config.nerd_font.version,
                github_mirror=self.effective_github_mirror,
            )
            and should_exit
        ):
            exit(1)

        return True

    def to_dict(self, config: ResolvedBuildConfig | None = None) -> dict[str, Any]:
        data = asdict(self)
        if config is not None:
            data["use_font_patcher"] = self.resolve_font_patcher_usage(
                config, should_exit=False
            )
        return data


class BuildConfigResolver:
    def __init__(self, project_root: str | Path = ".", version_tag: str = "v7.9"):
        self.project_root = Path(project_root)
        self.version_tag = version_tag

    def load_defaults(self) -> ResolvedBuildConfig:
        config = ResolvedBuildConfig(
            behavior=BuildBehaviorConfig(),
            feature=FeatureBuildConfig(),
            nerd_font=NerdFontBuildConfig(),
            cjk=CJKBuildSelection(),
            identity=BuildIdentityConfig(),
            metrics=BuildMetricsConfig(
                weight_mapping=default_weight_mapping(),
            ),
            feature_freeze=default_feature_freeze(),
        )
        self._apply_identity(config)
        return config

    def resolve(self, args) -> ResolvedBuildConfig:
        config = self.load_defaults()
        self._apply_json_config(config)
        self._apply_cli_overrides(config, args)
        self._apply_identity(config)
        return config

    def _config_path(self) -> Path:
        return self.project_root / "config.json"

    def _apply_json_config(self, config: ResolvedBuildConfig) -> None:
        config_path = self._config_path()
        if not config_path.exists():
            print(f"🚨 Config file not found: {config_path}, use default config")
            return
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON in config file: {config_path}") from error

        if "family_name" in data:
            config.identity.base_family_name = str(data["family_name"])

        if "pool_size" in data:
            config.metrics.pool_size = int(data["pool_size"])
        if "use_hinted" in data:
            config.feature.hinted = bool(data["use_hinted"])
        if "enable_ligature" in data:
            config.feature.liga = bool(data["enable_ligature"])
        if "ligature" in data and data["ligature"] is not None:
            config.feature.liga = bool(data["ligature"])
        if "ttfautohint_param" in data:
            config.metrics.ttfautohint_param = dict(data["ttfautohint_param"])
        if "infinite_arrow" in data:
            config.feature.infinite_arrow = data["infinite_arrow"]
        if "line_height" in data:
            config.feature.line_height = float(data["line_height"])
        if "width" in data:
            config.feature.width = str(data["width"])
        if "github_mirror" in data:
            config.metrics.github_mirror = str(data["github_mirror"])
        if "weight_mapping" in data:
            config.metrics.weight_mapping = {
                **config.metrics.weight_mapping,
                **dict(data["weight_mapping"]),
            }
        if "remove_tag_liga" in data:
            config.feature.remove_tag_liga = bool(data["remove_tag_liga"])
        if "feature_freeze" in data:
            config.feature_freeze.update(dict(data["feature_freeze"]))
        if "formats" in data:
            config.behavior.formats = normalize_build_formats(data["formats"])
        if "nerd_font" in data:
            nerd_font = dict(data["nerd_font"])
            if "enable" in nerd_font:
                config.nerd_font.enable = bool(nerd_font["enable"])
            if "version" in nerd_font:
                config.nerd_font.version = str(nerd_font["version"])
            if "mono" in nerd_font:
                config.nerd_font.mono = bool(nerd_font["mono"])
            if "propo" in nerd_font:
                config.nerd_font.propo = bool(nerd_font["propo"])
            if "use_font_patcher" in nerd_font:
                config.nerd_font.use_font_patcher = bool(nerd_font["use_font_patcher"])
            if "glyphs" in nerd_font:
                config.nerd_font.glyphs = list(nerd_font["glyphs"])
            if "extra_args" in nerd_font:
                config.nerd_font.extra_args = list(nerd_font["extra_args"])

        config.cjk = self._resolve_cjk_selection(data.get("cjk"), data.get("cn"))

    def _resolve_cjk_selection(
        self,
        raw_cjk: dict[str, Any] | None,
        legacy_cn: dict[str, Any] | None,
    ) -> CJKBuildSelection:
        selection = CJKBuildSelection()
        if raw_cjk:
            selection.enabled_locales = normalize_cjk_locale_list(
                raw_cjk.get("enabled_locales", [])
            )
            raw_locales = raw_cjk.get("locales", {})
            for locale in CJK_LOCALES:
                override = raw_locales.get(locale, {})
                if isinstance(override, dict):
                    self._merge_cjk_locale_config(selection.locales[locale], override)

        if legacy_cn and isinstance(legacy_cn, dict):
            self._merge_cjk_locale_config(selection.locales["cn"], legacy_cn)
            if legacy_cn.get("enable"):
                enabled = set(selection.enabled_locales)
                enabled.add("cn")
                selection.enabled_locales = [
                    locale for locale in CJK_LOCALES if locale in enabled
                ]

        selection.sync_enabled()
        return selection

    def _merge_cjk_locale_config(
        self, config: CJKLocaleConfig, override: dict[str, Any]
    ) -> None:
        for key, value in override.items():
            if key in {"enable", "use_wenyuan"}:
                continue
            if key == "scale_factor":
                config.scale_factor = parse_scale_factor(value)
            elif key == "transform_override" and isinstance(value, dict):
                config.transform_override = dict(value)
            elif hasattr(config, key):
                setattr(config, key, value)

    def _apply_cli_overrides(self, config: ResolvedBuildConfig, args) -> None:
        config.behavior.archive = bool(args.archive)
        config.behavior.debug = bool(args.debug)
        config.behavior.cache = bool(args.cache)
        config.behavior.least_styles = bool(args.least_styles)
        config.behavior.apply_fea_file = bool(args.apply_fea_file)
        config.behavior.cjk_output_format = args.cjk_format
        config.behavior.use_cn_both = bool(args.cn_both)

        if args.cn_both:
            print("⚠️ `--cn-both` is deprecated and kept for compatibility only.")

        if args.formats is not None:
            config.behavior.formats = list(args.formats)

        if args.ttf_only:
            print("⚠️ `--ttf-only` is deprecated. Use `--format ttf` instead.")
            config.behavior.formats = ["ttf"]

        if args.normal:
            config.feature.normal = True
            for feature in normal_enabled_features:
                config.feature_freeze[feature] = "enable"

        if args.feat:
            config.feature.feat = list(args.feat)
            for feature in args.feat:
                if feature in config.feature_freeze:
                    config.feature_freeze[feature] = "enable"

        if args.hinted is not None:
            config.feature.hinted = bool(args.hinted)
        if args.liga is not None:
            config.feature.liga = bool(args.liga)
        if args.infinite_arrow:
            config.feature.infinite_arrow = True
        if args.remove_tag_liga:
            config.feature.remove_tag_liga = True
        if args.width is not None:
            config.feature.width = args.width
        if args.line_height is not None:
            config.feature.line_height = float(args.line_height)

        if config.debug:
            config.nerd_font.enable = False
        if args.nf_mono:
            config.nerd_font.mono = True
            config.nerd_font.enable = True
        if args.nf_propo:
            config.nerd_font.propo = True
            config.nerd_font.enable = True
        if args.nerd_font is not None:
            config.nerd_font.enable = bool(args.nerd_font)
        if args.font_patcher:
            config.nerd_font.use_font_patcher = True

        self._apply_cjk_cli_overrides(config, args)

    def _apply_cjk_cli_overrides(self, config: ResolvedBuildConfig, args) -> None:
        enabled_locales = set(config.cjk.enabled_locales)
        enabled_locales.update(normalize_cjk_locale_list(getattr(args, "cjk", None)))

        if args.cn is not None:
            print("⚠️ `--cn` is deprecated. Use `--cjk cn` instead.")
            if args.cn:
                enabled_locales.add("cn")
            else:
                enabled_locales.discard("cn")

        override_locales = self._resolve_cjk_override_locales(config, enabled_locales)
        if args.cjk_narrow:
            for locale in override_locales:
                config.cjk.locales[locale].narrow = True
        if args.cjk_scale_factor is not None:
            for locale in override_locales:
                config.cjk.locales[locale].scale_factor = args.cjk_scale_factor

        if args.cn_narrow:
            print("⚠️ `--cn-narrow` is deprecated. Use `--cjk-narrow` instead.")
            config.cjk.locales["cn"].narrow = True
        if args.cn_scale_factor is not None:
            print("⚠️ `--cn-scale-factor` is deprecated. Use `--cjk-scale-factor` instead.")
            config.cjk.locales["cn"].scale_factor = args.cn_scale_factor
        if args.cn_rebuild:
            print(
                "⚠️ `--cn-rebuild` is deprecated. Use `task.py cjk --preset cn` for preset rebuilds."
            )
            enabled_locales.add("cn")

        config.cjk.enabled_locales = [
            locale for locale in CJK_LOCALES if locale in enabled_locales
        ]
        config.cjk.sync_enabled()

    def _resolve_cjk_override_locales(
        self, config: ResolvedBuildConfig, enabled_locales: set[str]
    ) -> list[str]:
        selected = [locale for locale in CJK_LOCALES if locale in enabled_locales]
        if selected:
            return selected
        configured = [
            locale for locale in config.cjk.enabled_locales if locale in CJK_LOCALES
        ]
        return configured or ["cn"]

    def _apply_identity(self, config: ResolvedBuildConfig) -> None:
        version_tag = self.version_tag
        base_name = config.identity.base_family_name
        name_parts = [word.capitalize() for word in base_name.split(" ")]
        if config.feature.normal:
            name_parts.append("Normal")
        if not config.feature.liga:
            name_parts.append("NL")

        width_name = config.get_width_name()
        if width_name:
            name_parts.append(width_name)
        if config.debug:
            name_parts.append("Debug")

        version_core = version_tag
        beta = None
        if "-" in version_tag:
            version_core, beta = version_tag.split("-", 1)

        major, minor = version_core.split(".")
        if major.startswith("v"):
            major = major[1:]

        config.identity.family_name = " ".join(name_parts)
        config.identity.family_name_compact = "".join(name_parts)
        config.identity.version_tag = version_tag
        config.identity.version = f"{major}.{minor}"
        config.identity.version_str = f"Version {major}.{minor:03}"
        config.identity.beta = beta


__all__ = [
    "BuildConfigResolver",
    "ResolvedBuildConfig",
    "RuntimeBuildPlan",
]

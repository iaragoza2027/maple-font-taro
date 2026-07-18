from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from os import environ, listdir, path
from pathlib import Path
import shutil
from typing import Any, Literal

from scripts.config.base import (
    BuildBehaviorConfig,
    BuildIdentityConfig,
    BuildMetricsConfig,
    BUILTIN_CJK_LOCALES,
    BuiltinCJKLocaleId,
    CJKBuildSelection,
    CJKCommonBuildOptions,
    CJKLocaleSelection,
    CustomCJKEntryConfig,
    FeatureBuildConfig,
    NerdFontBuildConfig,
    ResolvedCJKBuildEntry,
    ResolvedBuildConfig,
    default_feature_freeze,
    default_weight_mapping,
    normalize_build_formats,
    normalize_cjk_locale_list,
    parse_scale_factor,
)
from scripts.utils.errors import BuildDependencyError
from scripts.cjk.config import config_from_data
from scripts.cjk.models import CJKBuildConfig
from scripts.cjk.presets import build_preset_config, get_preset
from scripts.utils.downloads import check_font_patcher, download_zip_and_extract
from scripts.utils.files import join_path
from scripts.utils.process import get_font_forge_bin
from scripts.feature.compiler import normal_enabled_features
from scripts.utils.files import get_directory_hash


def check_file_count(
    dir_path: str, min_count: int = 16, end: str | None = None
) -> bool:
    if not path.isdir(dir_path):
        return False
    return (
        len([file for file in listdir(dir_path) if end is None or file.endswith(end)])
        >= min_count
    )


CJK_STATIC_DOWNLOAD_LOCALES = frozenset(BUILTIN_CJK_LOCALES)
CJKStaticBaseSource = Literal["local-cache", "download", "variable"]


@dataclass(frozen=True, slots=True)
class CJKStaticBaseResolution:
    static_dir: Path
    static_file_prefix: str
    source_kind: CJKStaticBaseSource


@dataclass(slots=True)
class BuildRuntimeContext:
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
    resolved_vertical_metric: tuple[int, int]

    @classmethod
    def from_config(cls, config: ResolvedBuildConfig) -> BuildRuntimeContext:
        output_root = "fonts"
        output_ttf = join_path(output_root, "TTF")
        output_ttf_hinted = join_path(output_root, "TTF-AutoHint")
        return cls(
            src_dir="source",
            output_root=output_root,
            output_otf=join_path(output_root, "OTF"),
            output_ttf=output_ttf,
            output_ttf_hinted=output_ttf_hinted,
            output_variable=join_path(output_root, "Variable"),
            output_woff2=join_path(output_root, "Woff2"),
            output_nf=join_path(output_root, "NF"),
            ttf_base_dir=output_ttf_hinted if config.use_hinted else output_ttf,
            has_cache=(
                check_file_count(
                    join_path(output_root, "Variable"), min_count=2, end=".ttf"
                )
                and check_file_count(output_ttf, min_count=4, end=".ttf")
                and check_file_count(output_ttf_hinted, min_count=4, end=".ttf")
                and (
                    not config.wants_format("otf")
                    or check_file_count(
                        join_path(output_root, "OTF"),
                        min_count=4,
                        end=".otf",
                    )
                )
                and (
                    not config.wants_format("woff2")
                    or check_file_count(
                        join_path(output_root, "Woff2"),
                        min_count=4,
                        end=".woff2",
                    )
                )
            ),
            is_nf_built=False,
            is_cjk_built=False,
            effective_github_mirror=environ.get("GITHUB", config.github_mirror),
            font_forge_bin=get_font_forge_bin(),
            resolved_vertical_metric=config.vertical_metric,
        )

    @property
    def output_dir(self) -> str:
        return self.output_root

    def feature_file_path(self, is_italic: bool, is_cjk: bool = False) -> str:
        return join_path(
            self.src_dir,
            "features",
            ("italic" if is_italic else "regular") + ("_cn" if is_cjk else "") + ".fea",
        )

    def cjk_static_dir(self, preset_config: CJKBuildConfig) -> Path:
        return preset_config.output.dir / preset_config.output.static_dir

    def cjk_static_hash_path(self, preset_config: CJKBuildConfig) -> Path:
        return preset_config.output.dir / preset_config.output.static_hash

    def cjk_static_archive_name(self, locale: BuiltinCJKLocaleId) -> str:
        return f"{locale}-static.zip"

    def cjk_static_download_url(self, locale: BuiltinCJKLocaleId) -> str:
        archive_name = self.cjk_static_archive_name(locale)
        return (
            f"https://{self.effective_github_mirror}/subframe7536/maple-font/"
            f"releases/download/cjk-base/{archive_name}"
        )

    def static_style_names(
        self,
        static_dir: Path,
        static_file_prefix: str,
    ) -> set[str]:
        if not static_dir.is_dir():
            return set()
        prefix = f"{static_file_prefix}-"
        return {
            font_path.stem.removeprefix(prefix)
            for font_path in static_dir.glob("*.ttf")
            if font_path.name.startswith(prefix)
        }

    def missing_cjk_static_styles(
        self,
        static_dir: Path,
        static_file_prefix: str,
        required_styles: list[str],
    ) -> list[str]:
        available_styles = self.static_style_names(static_dir, static_file_prefix)
        return [style for style in required_styles if style not in available_styles]

    def has_valid_cjk_static_hash(
        self,
        static_dir: Path,
        hash_path: Path,
    ) -> bool:
        if not static_dir.is_dir() or not hash_path.is_file():
            return False
        return hash_path.read_text(encoding="utf-8").strip() == get_directory_hash(
            str(static_dir)
        )

    def has_valid_cjk_static_base(
        self,
        static_dir: Path,
        static_file_prefix: str,
        hash_path: Path,
        required_styles: list[str],
    ) -> bool:
        return not self.missing_cjk_static_styles(
            static_dir,
            static_file_prefix,
            required_styles,
        ) and self.has_valid_cjk_static_hash(static_dir, hash_path)

    def should_download_cjk_static_base(
        self, locale: BuiltinCJKLocaleId | None
    ) -> bool:
        return locale in CJK_STATIC_DOWNLOAD_LOCALES

    def download_cjk_static_base(
        self,
        locale: BuiltinCJKLocaleId,
        preset_config: CJKBuildConfig,
    ) -> bool:
        if not self.should_download_cjk_static_base(locale):
            print(f"Skip CJK static base download for unsupported locale: {locale}")
            return False

        static_dir = self.cjk_static_dir(preset_config)
        static_dir.mkdir(parents=True, exist_ok=True)
        archive_name = self.cjk_static_archive_name(locale)
        return download_zip_and_extract(
            name=f"{preset_config.locale_name} static CJK base font",
            url=self.cjk_static_download_url(locale),
            zip_path=archive_name,
            output_dir=str(static_dir),
        )

    def build_cjk_static_base_from_variable(
        self,
        preset_config: CJKBuildConfig,
    ) -> None:
        from scripts.cjk.pipeline import build_cjk_fonts

        build_cjk_fonts(preset_config)

    def _resolve_local_cjk_static_base(
        self,
        clean_cache: bool,
        static_dir: Path,
        static_file_prefix: str,
        hash_path: Path,
        required_styles: list[str],
        locale_name: str,
    ) -> CJKStaticBaseResolution | None:
        if clean_cache:
            print(f"Clean CJK static base cache at {static_dir}")
            shutil.rmtree(static_dir, ignore_errors=True)
            return None

        if self.has_valid_cjk_static_base(
            static_dir,
            static_file_prefix,
            hash_path,
            required_styles,
        ):
            return CJKStaticBaseResolution(
                static_dir=static_dir,
                static_file_prefix=static_file_prefix,
                source_kind="local-cache",
            )

        local_missing_styles = self.missing_cjk_static_styles(
            static_dir,
            static_file_prefix,
            required_styles,
        )
        if local_missing_styles:
            print(
                f"Cached {locale_name} static fonts are incomplete: "
                f"{', '.join(local_missing_styles)}"
            )
        elif static_dir.exists():
            print(f"Cached {locale_name} static fonts failed hash check")

        shutil.rmtree(static_dir, ignore_errors=True)
        return None

    def _resolve_downloaded_cjk_static_base(
        self,
        locale: BuiltinCJKLocaleId | None,
        preset_config: CJKBuildConfig,
        static_dir: Path,
        static_file_prefix: str,
        hash_path: Path,
        required_styles: list[str],
    ) -> CJKStaticBaseResolution | None:
        if not locale or not self.should_download_cjk_static_base(locale):
            print(
                f"Skip CJK static base download for unsupported locale: {preset_config.locale_name}"
            )
            return None

        if not self.download_cjk_static_base(locale, preset_config):
            return None

        missing_styles = self.missing_cjk_static_styles(
            static_dir,
            static_file_prefix,
            required_styles,
        )
        if not missing_styles and self.has_valid_cjk_static_hash(static_dir, hash_path):
            return CJKStaticBaseResolution(
                static_dir=static_dir,
                static_file_prefix=static_file_prefix,
                source_kind="download",
            )

        print(
            f"Downloaded {preset_config.locale_name} static fonts are invalid; "
            "fallback to variable build"
        )
        shutil.rmtree(static_dir, ignore_errors=True)
        return None

    def _resolve_variable_cjk_static_base(
        self,
        preset_config: CJKBuildConfig,
        static_dir: Path,
        static_file_prefix: str,
        required_styles: list[str],
    ) -> CJKStaticBaseResolution:
        self.build_cjk_static_base_from_variable(preset_config)
        missing_styles = self.missing_cjk_static_styles(
            static_dir,
            static_file_prefix,
            required_styles,
        )
        if missing_styles:
            raise FileNotFoundError(
                f"Unable to resolve {preset_config.locale_name} static CJK base "
                f"font(s): missing style(s): {', '.join(missing_styles)}"
            )

        return CJKStaticBaseResolution(
            static_dir=static_dir,
            static_file_prefix=static_file_prefix,
            source_kind="variable",
        )

    def resolve_cjk_static_base(
        self,
        entry: ResolvedCJKBuildEntry,
        required_styles: list[str],
    ) -> CJKStaticBaseResolution:
        preset_config = entry.build_config
        static_dir = self.cjk_static_dir(preset_config)
        static_file_prefix = preset_config.naming.static_file_prefix
        hash_path = self.cjk_static_hash_path(preset_config)
        required_styles = sorted(set(required_styles))
        local_resolution = self._resolve_local_cjk_static_base(
            entry.common_options.clean_cache,
            static_dir,
            static_file_prefix,
            hash_path,
            required_styles,
            preset_config.locale_name,
        )
        if local_resolution is not None:
            return local_resolution

        download_resolution = self._resolve_downloaded_cjk_static_base(
            entry.download_locale,
            preset_config,
            static_dir,
            static_file_prefix,
            hash_path,
            required_styles,
        )
        if download_resolution is not None:
            return download_resolution

        return self._resolve_variable_cjk_static_base(
            preset_config,
            static_dir,
            static_file_prefix,
            required_styles,
        )

    def should_use_font_patcher(self, config: ResolvedBuildConfig) -> bool:
        if not (
            config.nerd_font.extra_args
            or config.nerd_font.use_font_patcher
            or config.nerd_font.glyphs != ["--complete"]
        ):
            return False
        return True

    def ensure_font_patcher_available(self, config: ResolvedBuildConfig) -> None:
        if not self.should_use_font_patcher(config):
            return
        if not self.font_forge_bin or not path.exists(self.font_forge_bin):
            raise BuildDependencyError(
                f"FontForge bin ({self.font_forge_bin}) not found, cannot build with Nerd Font Patcher"
            )
        if not check_font_patcher(
            version=config.nerd_font.version,
            github_mirror=self.effective_github_mirror,
        ):
            raise BuildDependencyError(
                "Nerd Font Patcher assets are unavailable for the requested version"
            )

    def to_dict(self, config: ResolvedBuildConfig | None = None) -> dict[str, Any]:
        data = asdict(self)
        if config is not None:
            data["use_font_patcher"] = self.should_use_font_patcher(config)
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
        selection = CJKBuildSelection(
            locales=self._resolve_cjk_locales(raw_cjk),
            common_options=self._resolve_cjk_common_options(raw_cjk),
        )
        self._apply_legacy_cn_config(selection, legacy_cn)
        selection.entries = self._build_cjk_entries(
            selection.locales,
            selection.common_options,
        )
        return selection

    def _resolve_cjk_locales(
        self,
        raw_cjk: dict[str, Any] | None,
    ) -> CJKLocaleSelection:
        selection = CJKLocaleSelection()
        if not isinstance(raw_cjk, dict):
            return selection

        raw_locales = raw_cjk.get("locales")
        if not isinstance(raw_locales, dict):
            return selection

        for locale in BUILTIN_CJK_LOCALES:
            selection.set_builtin_enabled(locale, bool(raw_locales.get(locale, False)))

        raw_custom = raw_locales.get("custom", [])
        if isinstance(raw_custom, list):
            for raw_entry in raw_custom:
                if not isinstance(raw_entry, dict):
                    continue
                entry_data = dict(raw_entry)
                enable = bool(entry_data.pop("enable", True))
                selection.custom.append(
                    CustomCJKEntryConfig(
                        enable=enable,
                        build_config=config_from_data(entry_data, self.project_root),
                    )
                )

        return selection

    def _resolve_cjk_common_options(
        self,
        raw_cjk: dict[str, Any] | None,
    ) -> CJKCommonBuildOptions:
        options = CJKCommonBuildOptions()
        if not isinstance(raw_cjk, dict):
            return options

        for key in (
            "with_nerd_font",
            "fix_meta_table",
            "clean_cache",
            "narrow",
            "use_hinted",
        ):
            if key in raw_cjk:
                setattr(options, key, bool(raw_cjk[key]))
        if "scale_factor" in raw_cjk:
            options.scale_factor = parse_scale_factor(raw_cjk["scale_factor"])
        return options

    def _apply_legacy_cn_config(
        self,
        selection: CJKBuildSelection,
        legacy_cn: dict[str, Any] | None,
    ) -> None:
        if not isinstance(legacy_cn, dict):
            return

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

    def _build_cjk_entries(
        self,
        locale_selection: CJKLocaleSelection,
        common_options: CJKCommonBuildOptions,
    ) -> list[ResolvedCJKBuildEntry]:
        entries: list[ResolvedCJKBuildEntry] = []
        used_entry_ids: set[str] = set()
        used_locale_names: set[str] = set()

        for preset_id in locale_selection.builtin_enabled_locales():
            preset_spec = get_preset(preset_id)
            preset_config = build_preset_config(preset_id)
            entries.append(
                ResolvedCJKBuildEntry(
                    entry_id=preset_id,
                    locale_name=preset_config.locale_name,
                    build_config=preset_config,
                    common_options=replace(common_options),
                    is_builtin=True,
                    preset_id=preset_id,
                    preset_spec=preset_spec,
                )
            )

        for custom_entry in locale_selection.custom:
            if not custom_entry.enable:
                continue
            locale_name = custom_entry.build_config.locale_name
            entries.append(
                ResolvedCJKBuildEntry(
                    entry_id=f"custom:{locale_name.lower()}",
                    locale_name=locale_name,
                    build_config=custom_entry.build_config,
                    common_options=replace(common_options),
                    is_builtin=False,
                )
            )

        for entry in entries:
            locale_key = entry.locale_name.lower()
            if entry.entry_id in used_entry_ids:
                raise ValueError(f"Duplicate CJK build entry id: {entry.entry_id}")
            if locale_key in used_locale_names:
                raise ValueError(
                    f"Duplicate CJK locale_name detected in build entries: {entry.locale_name}"
                )
            used_entry_ids.add(entry.entry_id)
            used_locale_names.add(locale_key)

        return entries

    def _apply_cli_overrides(self, config: ResolvedBuildConfig, args) -> None:
        config.behavior.archive = bool(args.archive)
        config.behavior.debug = bool(args.debug)
        config.behavior.cache = bool(args.cache)
        config.behavior.least_styles = bool(args.least_styles)
        config.behavior.apply_fea_file = bool(args.apply_fea_file)
        config.behavior.cjk_output_format = args.cjk_format
        config.behavior.use_cjk_both = bool(args.cjk_both or args.cn_both)

        if args.cn_both:
            print("⚠️ `--cn-both` is deprecated. Use `--cjk-both` instead.")

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
        enabled_locales = set(config.cjk.locales.builtin_enabled_locales())
        enabled_locales.update(normalize_cjk_locale_list(getattr(args, "cjk", None)))

        if args.cn is not None:
            print("⚠️ `--cn` is deprecated. Use `--cjk cn` instead.")
            if args.cn:
                enabled_locales.add("cn")
            else:
                enabled_locales.discard("cn")

        if args.cjk_narrow:
            config.cjk.common_options.narrow = True
        if args.cjk_scale_factor is not None:
            config.cjk.common_options.scale_factor = args.cjk_scale_factor

        if args.cn_narrow:
            print("⚠️ `--cn-narrow` is deprecated. Use `--cjk-narrow` instead.")
            config.cjk.common_options.narrow = True
        if args.cn_scale_factor is not None:
            print(
                "⚠️ `--cn-scale-factor` is deprecated. Use `--cjk-scale-factor` instead."
            )
            config.cjk.common_options.scale_factor = args.cn_scale_factor
        if args.cn_rebuild:
            print(
                "⚠️ `--cn-rebuild` is deprecated. Use `task.py cjk --preset cn` for preset rebuilds."
            )
            enabled_locales.add("cn")

        for locale in BUILTIN_CJK_LOCALES:
            config.cjk.locales.set_builtin_enabled(locale, locale in enabled_locales)
        config.cjk.entries = self._build_cjk_entries(
            config.cjk.locales,
            config.cjk.common_options,
        )

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
    "BuildRuntimeContext",
    "ResolvedBuildConfig",
]

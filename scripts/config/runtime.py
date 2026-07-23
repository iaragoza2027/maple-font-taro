from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from os import environ, listdir, path
from pathlib import Path
from typing import Any, Callable, Literal

from scripts.cjk.config import CJKBuildConfig
from scripts.config.base import (
    BUILTIN_CJK_LOCALES,
    BuiltinCJKLocaleId,
    ResolvedCJKBuildEntry,
    ResolvedConfig,
)
from scripts.utils.downloads import download_zip_and_extract
from scripts.utils.files import get_directory_hash, join_path
from scripts.utils.logging import logger
from scripts.utils.process import get_font_forge_bin


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
    def from_config(cls, config: ResolvedConfig) -> BuildRuntimeContext:
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
                and (
                    not config.needs_hinted_ttf()
                    or check_file_count(output_ttf_hinted, min_count=4, end=".ttf")
                )
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
            "https://github.com/subframe7536/maple-font/"
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
            logger.info("Skip CJK static base download: unsupported locale=%s", locale)
            return False

        static_dir = self.cjk_static_dir(preset_config)
        static_dir.mkdir(parents=True, exist_ok=True)
        archive_name = self.cjk_static_archive_name(locale)
        return download_zip_and_extract(
            name=f"{preset_config.locale_name} static CJK base font",
            url=self.cjk_static_download_url(locale),
            zip_path=archive_name,
            output_dir=str(static_dir),
            github_mirror=self.effective_github_mirror,
        )

    def build_cjk_static_base_from_variable(
        self,
        preset_config: CJKBuildConfig,
        build_config: ResolvedConfig,
        builder: Callable[..., None],
    ) -> None:
        builder(
            preset_config,
            build_config,
            github_mirror=self.effective_github_mirror,
        )

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
            logger.info("Clean CJK static base cache: path=%s", static_dir)
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
            logger.warning(
                "Cached CJK static fonts are incomplete: locale=%s, styles=%s",
                locale_name,
                ", ".join(local_missing_styles),
            )
        elif static_dir.exists():
            logger.warning(
                "Cached CJK static fonts failed hash check: locale=%s", locale_name
            )

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
            logger.info(
                "Skip CJK static base download: unsupported locale=%s",
                preset_config.locale_name,
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

        logger.warning(
            "Downloaded CJK static fonts are invalid; falling back to variable build: locale=%s",
            preset_config.locale_name,
        )
        shutil.rmtree(static_dir, ignore_errors=True)
        return None

    def _resolve_variable_cjk_static_base(
        self,
        preset_config: CJKBuildConfig,
        static_dir: Path,
        static_file_prefix: str,
        required_styles: list[str],
        build_config: ResolvedConfig,
        builder: Callable[..., None],
    ) -> CJKStaticBaseResolution:
        self.build_cjk_static_base_from_variable(
            preset_config,
            build_config,
            builder,
        )
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
        font_config: ResolvedConfig,
        variable_builder: Callable[..., None],
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
            font_config,
            variable_builder,
        )

    def to_dict(self, config: ResolvedConfig | None = None) -> dict[str, Any]:
        data = asdict(self)
        if config is not None:
            data["use_font_patcher"] = bool(
                config.nerd_font.extra_args
                or config.nerd_font.use_font_patcher
                or config.nerd_font.glyphs != ["--complete"]
            )
        return data

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.config.cli import parse_args
from scripts.config.base import CJKCommonBuildOptions, ResolvedCJKBuildEntry
from scripts.utils.errors import BuildDependencyError
from scripts.config.resolver import BuildConfigResolver
from scripts.config.runtime import BuildRuntimeContext
from scripts.cjk.config import (
    CJKBuildConfig,
    CJKNamingConfig,
    CJKOutputConfig,
    CJKSourceConfig,
)
from scripts.cjk.presets import CJKPresetId, get_preset
from scripts.utils.files import get_directory_hash
from scripts.pipeline.nerd_fonts import (
    ensure_font_patcher_available,
    should_use_font_patcher,
)


def make_runtime_context(tmp_path: Path) -> BuildRuntimeContext:
    return BuildRuntimeContext(
        src_dir="source",
        output_root=str(tmp_path / "fonts"),
        output_otf=str(tmp_path / "fonts" / "OTF"),
        output_ttf=str(tmp_path / "fonts" / "TTF"),
        output_ttf_hinted=str(tmp_path / "fonts" / "TTF-AutoHint"),
        output_variable=str(tmp_path / "fonts" / "Variable"),
        output_woff2=str(tmp_path / "fonts" / "Woff2"),
        output_nf=str(tmp_path / "fonts" / "NF"),
        ttf_base_dir=str(tmp_path / "fonts" / "TTF-AutoHint"),
        has_cache=False,
        is_nf_built=False,
        is_cjk_built=False,
        effective_github_mirror="github.com",
        font_forge_bin=None,
        resolved_vertical_metric=(1020, -300),
    )


def make_font_config():
    return BuildConfigResolver().load_defaults()


class ProjectConfigResolutionTest(unittest.TestCase):
    def test_project_config_resolves_without_cli_namespace(self) -> None:
        config = BuildConfigResolver().resolve_project_config()

        self.assertEqual(config.family_name, "Maple Mono")
        self.assertEqual(config.formats, ["ttf", "otf", "woff2"])


def make_preset(tmp_path: Path, locale_name: str = "CN") -> CJKBuildConfig:
    locale_dir = tmp_path / locale_name.lower()
    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=tmp_path / "source.ttf",
            masters={100: {"wght": 100}, 400: {"wght": 400}, 800: {"wght": 800}},
        ),
        locale_name=locale_name,
        output=CJKOutputConfig(
            dir=locale_dir,
            regular_variable=f"MapleMono-{locale_name}-VF.ttf",
            italic_variable=f"MapleMono-{locale_name}-Italic-VF.ttf",
            static_dir="static",
            static_hash=f"static-{locale_name.lower()}.sha256",
            archive_name=f"{locale_name.lower()}-base-static.zip",
        ),
        naming=CJKNamingConfig(
            family_name=f"Maple Mono {locale_name}",
            postscript_prefix=f"MapleMono{locale_name}",
            static_file_prefix=f"MapleMono{locale_name}",
        ),
    )


def make_entry(
    tmp_path: Path,
    locale_name: str = "CN",
    preset_id: CJKPresetId | None = "cn",
    *,
    clean_cache: bool = False,
) -> ResolvedCJKBuildEntry:
    preset_spec = get_preset(preset_id) if preset_id else None
    return ResolvedCJKBuildEntry(
        entry_id=preset_id or f"custom:{locale_name.lower()}",
        locale_name=locale_name,
        build_config=make_preset(tmp_path, locale_name),
        common_options=CJKCommonBuildOptions(clean_cache=clean_cache),
        is_builtin=bool(preset_id),
        preset_id=preset_id,
        preset_spec=preset_spec,
    )


def write_static_fonts(static_dir: Path, prefix: str, styles: list[str]) -> None:
    static_dir.mkdir(parents=True, exist_ok=True)
    for style in styles:
        (static_dir / f"{prefix}-{style}.ttf").write_bytes(style.encode("utf-8"))


def write_static_hash(static_dir: Path, hash_path: Path) -> None:
    hash_path.parent.mkdir(parents=True, exist_ok=True)
    hash_path.write_text(get_directory_hash(str(static_dir)), encoding="utf-8")


def resolve_quietly(
    runtime_context: BuildRuntimeContext,
    entry: ResolvedCJKBuildEntry,
    required_styles: list[str],
):
    def build_variable(
        config: CJKBuildConfig,
        *_args,
        **_kwargs,
    ) -> None:
        write_static_fonts(
            runtime_context.cjk_static_dir(config),
            config.naming.static_file_prefix,
            required_styles,
        )

    with redirect_stdout(StringIO()):
        return runtime_context.resolve_cjk_static_base(
            entry,
            required_styles,
            make_font_config(),
            build_variable,
        )


class BuildRuntimeContextCJKStaticBaseTest(unittest.TestCase):
    def test_static_download_uses_effective_github_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_context = make_runtime_context(tmp_path)
            runtime_context.effective_github_mirror = "mirror.example.com/github.com"
            entry = make_entry(tmp_path)

            with patch(
                "scripts.config.runtime.download_zip_and_extract",
                return_value=True,
            ) as download:
                downloaded = runtime_context.download_cjk_static_base(
                    "cn",
                    entry.build_config,
                )

            self.assertTrue(downloaded)
            self.assertEqual(
                download.call_args.kwargs["github_mirror"],
                "mirror.example.com/github.com",
            )
            self.assertEqual(
                download.call_args.kwargs["url"],
                "https://github.com/subframe7536/maple-font/releases/download/cjk-base/cn-static.zip",
            )

    def test_variable_fallback_uses_effective_github_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_context = make_runtime_context(Path(tmp))
            runtime_context.effective_github_mirror = "mirror.example.com"
            config = make_preset(Path(tmp))

            with patch("scripts.cjk.builder.build_cjk_fonts") as build:
                runtime_context.build_cjk_static_base_from_variable(
                    config,
                    make_font_config(),
                    build,
                )

            build.assert_called_once_with(
                config,
                make_font_config(),
                github_mirror="mirror.example.com",
            )

    def test_reuses_valid_local_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_context = make_runtime_context(tmp_path)
            entry = make_entry(tmp_path)
            static_dir = runtime_context.cjk_static_dir(entry.build_config)
            write_static_fonts(
                static_dir,
                entry.build_config.naming.static_file_prefix,
                ["Regular"],
            )
            write_static_hash(
                static_dir,
                runtime_context.cjk_static_hash_path(entry.build_config),
            )

            result = resolve_quietly(runtime_context, entry, ["Regular"])

            self.assertEqual(result.source_kind, "local-cache")
            self.assertEqual(result.static_dir, static_dir)

    def test_mismatched_hash_attempts_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_context = make_runtime_context(tmp_path)
            entry = make_entry(tmp_path)
            static_dir = runtime_context.cjk_static_dir(entry.build_config)
            write_static_fonts(
                static_dir,
                entry.build_config.naming.static_file_prefix,
                ["Regular"],
            )
            runtime_context.cjk_static_hash_path(entry.build_config).write_text(
                "bad-hash",
                encoding="utf-8",
            )

            def fake_download(
                self: BuildRuntimeContext,
                locale: str,
                config: CJKBuildConfig,
            ) -> bool:
                write_static_fonts(
                    self.cjk_static_dir(config),
                    config.naming.static_file_prefix,
                    ["Regular"],
                )
                write_static_hash(
                    self.cjk_static_dir(config),
                    self.cjk_static_hash_path(config),
                )
                return True

            with patch.object(
                BuildRuntimeContext,
                "download_cjk_static_base",
                fake_download,
            ):
                with patch.object(
                    BuildRuntimeContext,
                    "build_cjk_static_base_from_variable",
                ) as build_mock:
                    result = resolve_quietly(runtime_context, entry, ["Regular"])

            self.assertEqual(result.source_kind, "download")
            build_mock.assert_not_called()

    def test_custom_entry_skips_download_and_uses_variable_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_context = make_runtime_context(tmp_path)
            entry = make_entry(tmp_path, locale_name="HK", preset_id=None)

            def fake_build(
                self: BuildRuntimeContext,
                config: CJKBuildConfig,
                *_args,
            ) -> None:
                write_static_fonts(
                    self.cjk_static_dir(config),
                    config.naming.static_file_prefix,
                    ["Regular"],
                )

            with patch.object(
                BuildRuntimeContext,
                "download_cjk_static_base",
                return_value=True,
            ) as download_mock:
                with patch.object(
                    BuildRuntimeContext,
                    "build_cjk_static_base_from_variable",
                    fake_build,
                ):
                    result = resolve_quietly(runtime_context, entry, ["Regular"])

            download_mock.assert_not_called()
            self.assertEqual(result.source_kind, "variable")

    def test_variable_fallback_skips_hash_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_context = make_runtime_context(tmp_path)
            entry = make_entry(tmp_path)

            def fake_build(
                self: BuildRuntimeContext,
                config: CJKBuildConfig,
                *_args,
            ) -> None:
                write_static_fonts(
                    self.cjk_static_dir(config),
                    config.naming.static_file_prefix,
                    ["Regular"],
                )

            with patch.object(
                BuildRuntimeContext,
                "download_cjk_static_base",
                return_value=False,
            ):
                with patch.object(
                    BuildRuntimeContext,
                    "build_cjk_static_base_from_variable",
                    fake_build,
                ):
                    result = resolve_quietly(runtime_context, entry, ["Regular"])

            self.assertEqual(result.source_kind, "variable")
            self.assertFalse(
                runtime_context.cjk_static_hash_path(entry.build_config).exists()
            )

    def test_missing_styles_after_fallback_raise_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_context = make_runtime_context(tmp_path)
            entry = make_entry(tmp_path)

            with patch.object(
                BuildRuntimeContext,
                "download_cjk_static_base",
                return_value=False,
            ):
                with patch.object(
                    BuildRuntimeContext,
                    "build_cjk_static_base_from_variable",
                    return_value=None,
                ):
                    with self.assertRaisesRegex(FileNotFoundError, "missing style"):
                        resolve_quietly(runtime_context, entry, ["Regular"])


class BuildConfigResolverJsonTest(unittest.TestCase):
    def test_rejects_non_object_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                BuildConfigResolver(project_root=Path(tmp)).resolve(parse_args([]))


class BuildConfigResolverCJKEntryTest(unittest.TestCase):
    def _resolve_with_config(
        self,
        config_data: dict,
        args: list[str] | None = None,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "config.json").write_text(
                json.dumps(config_data),
                encoding="utf-8",
            )
            resolver = BuildConfigResolver(project_root=tmp_path)
            return resolver.resolve(parse_args(args or []))

    def test_builtin_locale_booleans_resolve_to_entries(self) -> None:
        font_config = self._resolve_with_config(
            {
                "cjk": {
                    "locales": {
                        "cn": True,
                        "jp": False,
                        "tc": True,
                        "kr": False,
                        "custom": [],
                    }
                }
            }
        )

        self.assertEqual(
            [entry.entry_id for entry in font_config.get_selected_cjk_entries()],
            ["cn", "tc"],
        )

    def test_cjk_format_resolves_from_project_config(self) -> None:
        font_config = self._resolve_with_config(
            {
                "cjk": {
                    "format": "variable",
                    "locales": {},
                }
            }
        )

        self.assertEqual(font_config.cjk_output_format, "variable")

    def test_cjk_format_cli_override_takes_precedence(self) -> None:
        font_config = self._resolve_with_config(
            {
                "cjk": {
                    "format": "variable",
                    "locales": {},
                }
            },
            ["--cjk-format", "static"],
        )

        self.assertEqual(font_config.cjk_output_format, "static")

    def test_rejects_unsupported_cjk_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported CJK output format"):
            self._resolve_with_config(
                {
                    "cjk": {
                        "format": "woff2",
                        "locales": {},
                    }
                }
            )

    def test_custom_enable_controls_resolved_entries(self) -> None:
        font_config = self._resolve_with_config(
            {
                "cjk": {
                    "locales": {
                        "cn": False,
                        "jp": False,
                        "tc": False,
                        "kr": False,
                        "custom": [
                            {
                                "enable": True,
                                "locale_name": "HK",
                                "source": {
                                    "path": "hk.ttf",
                                    "masters": {
                                        "100": {"wght": 100},
                                        "400": {"wght": 400},
                                        "800": {"wght": 800},
                                    },
                                },
                            },
                            {
                                "enable": False,
                                "locale_name": "MO",
                                "source": {
                                    "path": "mo.ttf",
                                    "masters": {
                                        "100": {"wght": 100},
                                        "400": {"wght": 400},
                                        "800": {"wght": 800},
                                    },
                                },
                            },
                        ],
                    }
                }
            }
        )

        entries = font_config.get_selected_cjk_entries()
        self.assertEqual([entry.entry_id for entry in entries], ["custom:hk"])
        self.assertEqual(entries[0].locale_name, "HK")

    def test_cjk_cli_only_enables_builtin_entries(self) -> None:
        font_config = self._resolve_with_config(
            {
                "cjk": {
                    "locales": {
                        "cn": False,
                        "jp": False,
                        "tc": False,
                        "kr": False,
                        "custom": [
                            {
                                "enable": True,
                                "locale_name": "HK",
                                "source": {
                                    "path": "hk.ttf",
                                    "masters": {
                                        "100": {"wght": 100},
                                        "400": {"wght": 400},
                                        "800": {"wght": 800},
                                    },
                                },
                            }
                        ],
                    }
                }
            },
            ["--cjk", "jp"],
        )

        self.assertEqual(
            [entry.entry_id for entry in font_config.get_selected_cjk_entries()],
            ["jp", "custom:hk"],
        )


class BuildConfigResolverCodepointAliasTest(unittest.TestCase):
    def _resolve(self, codepoint_alias):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_text(
                json.dumps({"codepoint_alias": codepoint_alias}),
                encoding="utf-8",
            )
            return BuildConfigResolver(project_root=root).resolve(parse_args([]))

    def test_resolves_and_serializes_extra_codepoint_aliases(self) -> None:
        font_config = self._resolve({"0xE000": "0x004B"})

        self.assertEqual(font_config.codepoint_alias, {0xE000: 0x004B})
        self.assertEqual(
            font_config.to_dict()["metrics"]["codepoint_alias"],
            {"0xE000": "0x004B"},
        )
        self.assertEqual(
            font_config.to_build_record()["codepoint_alias"],
            {"0xE000": "0x004B"},
        )

    def test_empty_mapping_adds_no_extra_aliases(self) -> None:
        self.assertEqual(self._resolve({}).codepoint_alias, {})

    def test_rejects_invalid_unicode_scalars(self) -> None:
        for mapping in (
            {"2126": "0x03A9"},
            {"0x110000": "0x004B"},
            {"0xE000": "0xD800"},
            {"0xE000": "0xE000"},
        ):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                self._resolve(mapping)

    def test_rejects_overriding_builtin_alias(self) -> None:
        with self.assertRaisesRegex(ValueError, "built in"):
            self._resolve({"0x212A": "0x0041"})


class NerdFontDependencyTest(unittest.TestCase):
    def test_should_use_font_patcher_is_pure_decision(self) -> None:
        font_config = make_font_config()

        self.assertFalse(should_use_font_patcher(font_config))

        font_config.nerd_font.use_font_patcher = True
        self.assertTrue(should_use_font_patcher(font_config))

    def test_ensure_font_patcher_available_raises_for_missing_fontforge(self) -> None:
        runtime_context = make_runtime_context(Path("."))
        font_config = make_font_config()
        font_config.nerd_font.use_font_patcher = True

        with self.assertRaisesRegex(BuildDependencyError, "FontForge bin"):
            ensure_font_patcher_available(font_config, runtime_context)

    def test_ensure_font_patcher_available_raises_for_missing_patcher_assets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fontforge_bin = tmp_path / "fontforge"
            fontforge_bin.write_text("", encoding="utf-8")

            runtime_context = make_runtime_context(tmp_path)
            runtime_context.font_forge_bin = str(fontforge_bin)
            font_config = make_font_config()
            font_config.nerd_font.use_font_patcher = True

            with patch(
                "scripts.pipeline.nerd_fonts.check_font_patcher",
                return_value=False,
            ):
                with self.assertRaisesRegex(
                    BuildDependencyError,
                    "Nerd Font Patcher assets",
                ):
                    ensure_font_patcher_available(font_config, runtime_context)


class BuildRuntimeContextCacheTest(unittest.TestCase):
    def test_cache_skips_hinted_directory_when_not_required(self) -> None:
        font_config = make_font_config()
        font_config.behavior.formats = ["otf"]
        font_config.nerd_font.enable = False
        checked_paths: list[str] = []

        def record_check(dir_path: str, **_kwargs) -> bool:
            checked_paths.append(dir_path)
            return True

        with (
            patch("scripts.config.runtime.check_file_count", record_check),
            patch("scripts.config.runtime.get_font_forge_bin", return_value=None),
        ):
            runtime_context = BuildRuntimeContext.from_config(font_config)

        self.assertTrue(runtime_context.has_cache)
        self.assertFalse(any(path.endswith("TTF-AutoHint") for path in checked_paths))

    def test_cache_requires_hinted_directory_for_ttf_outputs(self) -> None:
        font_config = make_font_config()

        def reject_hinted(dir_path: str, **_kwargs) -> bool:
            return not dir_path.endswith("TTF-AutoHint")

        with (
            patch("scripts.config.runtime.check_file_count", reject_hinted),
            patch("scripts.config.runtime.get_font_forge_bin", return_value=None),
        ):
            runtime_context = BuildRuntimeContext.from_config(font_config)

        self.assertFalse(runtime_context.has_cache)


if __name__ == "__main__":
    unittest.main()

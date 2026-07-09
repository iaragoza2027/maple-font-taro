from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from source.py.build.config import (
    CJKCommonBuildOptions,
    ResolvedBuildConfig,
    ResolvedCJKBuildEntry,
)
from source.py.build.errors import BuildDependencyError
from source.py.build.resolver import BuildConfigResolver, BuildRuntimeContext
from source.py.build.util import check_ftcli, postprocess_cjk_extended_static_font
from source.py.cjk.config import CJKBuildConfig, CJKSourceConfig
from source.py.cjk.presets import build_preset_config, get_preset


def make_runtime_context() -> BuildRuntimeContext:
    return BuildRuntimeContext(
        src_dir="source",
        output_root="fonts",
        output_otf="fonts/OTF",
        output_ttf="fonts/TTF",
        output_ttf_hinted="fonts/TTF-AutoHint",
        output_variable="fonts/Variable",
        output_woff2="fonts/Woff2",
        output_nf="fonts/NF",
        ttf_base_dir="fonts/TTF-AutoHint",
        has_cache=False,
        is_nf_built=False,
        is_cjk_built=False,
        effective_github_mirror="github.com",
        font_forge_bin=None,
        resolved_vertical_metric=(1020, -300),
    )


def make_builtin_entry() -> ResolvedCJKBuildEntry:
    return ResolvedCJKBuildEntry(
        entry_id="cn",
        locale_name="CN",
        build_config=build_preset_config("cn"),
        common_options=CJKCommonBuildOptions(fix_meta_table=True),
        is_builtin=True,
        preset_id="cn",
        preset_spec=get_preset("cn"),
    )


def make_custom_entry() -> ResolvedCJKBuildEntry:
    return ResolvedCJKBuildEntry(
        entry_id="custom:hk",
        locale_name="HK",
        build_config=CJKBuildConfig(
            source=CJKSourceConfig(
                path=Path("source.ttf"),
                masters={100: {"wght": 100}, 400: {"wght": 400}, 800: {"wght": 800}},
            ),
            locale_name="HK",
        ),
        common_options=CJKCommonBuildOptions(fix_meta_table=True),
        is_builtin=False,
    )


class CheckFtcliTest(unittest.TestCase):
    def test_check_ftcli_raises_dependency_error_when_package_missing(self) -> None:
        with patch(
            "source.py.build.util.importlib.util.find_spec",
            side_effect=[None, None],
        ):
            with self.assertRaisesRegex(
                BuildDependencyError,
                "foundrytools-cli is not found",
            ):
                check_ftcli()


class PostprocessCJKStaticFontTest(unittest.TestCase):
    def test_builtin_entry_applies_meta_table(self) -> None:
        font_config = BuildConfigResolver().load_defaults()
        runtime_context = make_runtime_context()
        with patch("source.py.build.util.remove_target_glyph"), patch(
            "source.py.build.util.apply_cjk_names",
            return_value="MapleMono-CN-Regular",
        ), patch(
            "source.py.build.util.apply_cjk_width_transform",
            return_value=False,
        ), patch("source.py.build.util.apply_cjk_meta_table") as apply_meta_mock, patch(
            "source.py.build.util.apply_cjk_metrics"
        ), patch(
            "source.py.build.util.verify_cjk_widths"
        ), patch.object(ResolvedBuildConfig, "patch_font_feature"):
            postprocess_cjk_extended_static_font(
                object(),  # type: ignore[arg-type]
                make_builtin_entry(),
                font_config,
                runtime_context,
                "Regular",
            )

        apply_meta_mock.assert_called_once()

    def test_custom_entry_skips_meta_table_even_when_enabled(self) -> None:
        font_config = BuildConfigResolver().load_defaults()
        runtime_context = make_runtime_context()
        with patch("source.py.build.util.remove_target_glyph"), patch(
            "source.py.build.util.apply_cjk_names",
            return_value="MapleMono-HK-Regular",
        ), patch(
            "source.py.build.util.apply_cjk_width_transform",
            return_value=False,
        ), patch("source.py.build.util.apply_cjk_meta_table") as apply_meta_mock, patch(
            "source.py.build.util.apply_cjk_metrics"
        ), patch(
            "source.py.build.util.verify_cjk_widths"
        ), patch.object(ResolvedBuildConfig, "patch_font_feature"):
            postprocess_cjk_extended_static_font(
                object(),  # type: ignore[arg-type]
                make_custom_entry(),
                font_config,
                runtime_context,
                "Regular",
            )

        apply_meta_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

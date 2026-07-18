from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.config.base import ResolvedBuildConfig, normalize_feature_freeze
from scripts.feature.apply import patch_font_feature


class FeatureFreezeConfigTest(unittest.TestCase):
    def test_normalizes_enabled_disabled_and_ignored_features(self) -> None:
        self.assertEqual(
            normalize_feature_freeze(
                {
                    "cv01": "enabled",
                    "cv02": "disabled",
                    "cv03": "ignore",
                },
                calt=True,
            ),
            {"cv01": "1", "cv02": "-1", "cv03": "0", "calt": "1"},
        )

    def test_rejects_invalid_feature_freeze_value(self) -> None:
        with self.assertRaisesRegex(
            TypeError,
            r"Invalid freeze config item: \{ cv01: unexpected \}",
        ):
            normalize_feature_freeze({"cv01": "unexpected"}, calt=False)

    def test_resolved_config_uses_normalized_freeze_values(self) -> None:
        config = ResolvedBuildConfig(
            feature_freeze={"cv01": "enable", "cv02": "disable"}
        )
        config.feature.liga = False

        self.assertEqual(config.freeze_config_str, "-calt;+cv01;-cv02;")


class FeatureApplicationTest(unittest.TestCase):
    @patch("scripts.feature.apply.freeze_feature")
    @patch("scripts.feature.apply.get_freeze_moving_rules", return_value=["cv01"])
    @patch("scripts.feature.apply.addOpenTypeFeaturesFromString")
    @patch(
        "scripts.feature.apply.generate_fea_string",
        return_value="feature calt { } calt;",
    )
    def test_freezes_static_fonts_but_not_variable_fonts(
        self,
        generate_fea_string: MagicMock,
        add_features: MagicMock,
        moving_rules: MagicMock,
        freeze_feature: MagicMock,
    ) -> None:
        config = ResolvedBuildConfig()
        font = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            patch_font_feature(
                config,
                font,
                Path(tmp),
                is_italic=False,
                is_cn=False,
                is_variable=False,
                is_hinted=False,
                fea_path="",
            )
            patch_font_feature(
                config,
                font,
                Path(tmp),
                is_italic=False,
                is_cn=False,
                is_variable=True,
                is_hinted=False,
                fea_path="",
            )

        self.assertEqual(generate_fea_string.call_count, 2)
        self.assertEqual(add_features.call_count, 2)
        moving_rules.assert_called_once_with()
        freeze_feature.assert_called_once_with(
            font,
            ["cv01"],
            normalize_feature_freeze(config.feature_freeze, config.enable_ligature),
        )

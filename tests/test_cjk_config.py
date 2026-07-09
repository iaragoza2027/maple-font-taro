from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from source.py.cjk.config import add_cjk_arguments, config_from_json


class CJKConfigSurfaceTest(unittest.TestCase):
    def test_config_from_json_rejects_feature_font(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "custom.json"
            config_path.write_text(
                json.dumps(
                    {
                        "locale_name": "HK",
                        "feature_font": "feature.ttf",
                        "source": {
                            "path": "source.ttf",
                            "masters": {
                                "100": {"wght": 100},
                                "400": {"wght": 400},
                                "800": {"wght": 800},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "feature_font"):
                config_from_json(config_path)

    def test_add_cjk_arguments_does_not_expose_feature_font(self) -> None:
        parser = argparse.ArgumentParser()
        add_cjk_arguments(parser)

        self.assertNotIn(
            "feature_font",
            {action.dest for action in parser._actions},
        )

    def test_cjk_schema_removes_feature_font(self) -> None:
        schema = json.loads(Path("source/cjk/cjk_schema.json").read_text(encoding="utf-8"))

        self.assertNotIn("feature_font", schema["properties"])

    def test_top_level_schema_wraps_custom_entries_with_enable(self) -> None:
        schema = json.loads(Path("source/schema.json").read_text(encoding="utf-8"))
        custom_item = (
            schema["properties"]["cjk"]["properties"]["locales"]["properties"]["custom"][
                "items"
            ]
        )

        self.assertEqual(custom_item["allOf"][1]["properties"]["enable"]["type"], "boolean")


if __name__ == "__main__":
    unittest.main()

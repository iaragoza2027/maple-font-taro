from __future__ import annotations

import hashlib
import unittest

from scripts.feature.compiler import (
    generate_fea_string,
    generate_fea_string_cn_only,
    get_all_calt_text,
)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class FeatureGenerationContractTest(unittest.TestCase):
    def test_representative_feature_outputs_remain_stable(self) -> None:
        cases = {
            "regular": (
                generate_fea_string(is_italic=False, is_cn=False),
                "9ffbd5517279a81af617c9e4be5d5dcd38fe51437f6edc3010f74a3d3f432c31",
            ),
            "italic": (
                generate_fea_string(is_italic=True, is_cn=False),
                "f4516e6980b1c66a20f62ceb07c2f85d6e3701404a9aa86b2f20a894badf446f",
            ),
            "cn-only": (
                generate_fea_string_cn_only(),
                "d15731bd16c7776a261b11b39320c634840e1f79c519da8d533f84ad7b9d5f9a",
            ),
            "regular-cn": (
                generate_fea_string(is_italic=False, is_cn=True),
                "b3214b148999decdda793381538637c9058bb4c75b4c26b34d5fa2a5f42d1177",
            ),
            "without-infinite-arrows": (
                generate_fea_string(
                    is_italic=False,
                    is_cn=False,
                    enable_infinite=False,
                ),
                "c67f5b0c6d69ecf88994ad0308bfb23b7a989d242e7254e5dfba420e5dd93cde",
            ),
        }

        for label, (content, expected_hash) in cases.items():
            with self.subTest(label=label):
                self.assertEqual(content_hash(content), expected_hash)

    def test_calt_documentation_does_not_depend_on_previous_generation(self) -> None:
        generate_fea_string(
            is_italic=False,
            is_cn=False,
            enable_infinite=False,
        )
        after_disabled_generation = get_all_calt_text()
        generate_fea_string(
            is_italic=False,
            is_cn=False,
            enable_infinite=True,
        )
        after_enabled_generation = get_all_calt_text()

        self.assertEqual(after_disabled_generation, after_enabled_generation)
        self.assertEqual(
            content_hash(after_enabled_generation),
            "f6393e840f5f7d2d87d56c145083013d794f4a9088019a86e56fe130169e3bb7",
        )


if __name__ == "__main__":
    unittest.main()

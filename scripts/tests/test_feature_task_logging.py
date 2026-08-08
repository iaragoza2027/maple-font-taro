from __future__ import annotations

import unittest
from unittest.mock import call, patch

from scripts.task.fea import build_fea
from scripts.utils.files import join_path


class FeatureTaskLoggingTest(unittest.TestCase):
    def test_feature_task_logs_generated_and_synchronized_outputs(self) -> None:
        with (
            patch("scripts.task.fea.log_task") as log_task,
            patch("scripts.task.fea.logger.info") as log_info,
            patch("scripts.task.fea.generate_fea_string", return_value="feature"),
            patch("scripts.task.fea.generate_fea_string_cn_only", return_value="cn"),
            patch("scripts.task.fea.get_all_calt_text", return_value=""),
            patch("scripts.task.fea.get_cv_desc", return_value=""),
            patch("scripts.task.fea.get_cv_italic_desc", return_value=""),
            patch("scripts.task.fea.get_cv_cn_desc", return_value=""),
            patch("scripts.task.fea.get_ss_desc", return_value=""),
            patch("scripts.task.fea.get_total_feat_dict", return_value={}),
            patch("scripts.task.fea.get_freeze_moving_rules", return_value=[]),
            patch("scripts.task.fea.read_text", return_value="MOVING_RULES = []"),
            patch("scripts.task.fea.write_text"),
            patch("scripts.task.fea.replace_section") as replace_section,
            patch("scripts.task.fea.update_schema"),
            patch("scripts.task.fea.update_feature_freeze"),
        ):
            build_fea("generated")

        log_task.assert_called_once_with(
            "fea", "Generate feature files: output=%s", "generated"
        )
        messages = [call.args[0] % call.args[1:] for call in log_info.call_args_list]
        for filename in [
            "regular.fea",
            "italic.fea",
            "cn.fea",
            "regular_cn.fea",
            "italic_cn.fea",
        ]:
            self.assertIn(
                f"Saved feature file to {join_path('generated', filename)}", messages
            )
        self.assertIn(
            f"Synchronized feature schema: path={join_path('source', 'schema.json')}",
            messages,
        )
        self.assertIn("Synchronized feature configuration: path=config.json", messages)
        for border in [
            "<!-- CALT -->",
            "<!-- CV -->",
            "<!-- CV-IT -->",
            "<!-- CV-CN -->",
            "<!-- SS -->",
        ]:
            self.assertIn(
                call(join_path("docs", "opentype-features.md"), border, ""),
                replace_section.call_args_list,
            )
        self.assertIn(
            "Synchronized browser feature rules: "
            f"path={join_path('scripts', 'in_browser.py')}",
            messages,
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import unittest
from unittest.mock import patch

from scripts.task import cjk, nf


class TaskDownloadMirrorTest(unittest.TestCase):
    def test_cjk_task_passes_configured_mirror_to_builder(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        cjk.register_parser(subparsers)
        args = parser.parse_args(["cjk", "--preset", "cn", "--vf-only"])

        with (
            patch(
                "scripts.task.cjk.github_mirror_from_config",
                return_value="mirror.example.com/github.com",
            ),
            patch("scripts.task.cjk.build_cjk_fonts") as build,
        ):
            cjk.run(args)

        self.assertEqual(
            build.call_args.kwargs["github_mirror"],
            "mirror.example.com/github.com",
        )

    def test_nerd_font_task_passes_configured_mirror_to_download(self) -> None:
        with (
            patch(
                "scripts.task.nf.github_mirror_from_config",
                return_value="mirror.example.com/github.com",
            ),
            patch(
                "scripts.task.nf.download_json",
                return_value={"tag_name": "v3.2.1"},
            ) as download_metadata,
            patch("scripts.task.nf.check_font_patcher", return_value=True) as check,
            patch("scripts.task.nf.update_config_json"),
        ):
            nf.check_update()

        check.assert_called_once()
        self.assertEqual(check.call_args.args[1], "mirror.example.com/github.com")
        self.assertEqual(
            download_metadata.call_args.args[1],
            "mirror.example.com/github.com",
        )


if __name__ == "__main__":
    unittest.main()

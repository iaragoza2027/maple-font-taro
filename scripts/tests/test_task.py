from __future__ import annotations

import json
import unittest
from pathlib import Path
from stat import S_IMODE
from tempfile import TemporaryDirectory

from scripts.task import nf


class TaskDownloadMirrorTest(unittest.TestCase):
    def test_update_config_json_replaces_shorter_version_without_stale_bytes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            config_path = self.write_config(Path(directory), "3.2.1000")

            nf.update_config_json(str(config_path), "3.2.1")

            self.assertEqual(self.read_version(config_path), "3.2.1")
            self.assertEqual(config_path.read_text(encoding="utf-8")[-1], "\n")

    def test_update_config_json_preserves_file_permissions(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = self.write_config(Path(directory), "3.2.0")
            config_path.chmod(0o640)
            original_mode = S_IMODE(config_path.stat().st_mode)

            nf.update_config_json(str(config_path), "3.2.1")

            self.assertEqual(S_IMODE(config_path.stat().st_mode), original_mode)

    def test_update_config_json_fails_clearly_for_missing_or_invalid_config(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            missing_path = directory_path / "missing.json"
            invalid_path = directory_path / "invalid.json"
            invalid_path.write_text("[]", encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                nf.update_config_json(str(missing_path), "3.2.1")
            with self.assertRaisesRegex(ValueError, "expected an object"):
                nf.update_config_json(str(invalid_path), "3.2.1")

    @staticmethod
    def write_config(directory: Path, version: str) -> Path:
        config_path = directory / "config.json"
        config_path.write_text(
            json.dumps({"nerd_font": {"version": version}}, indent=2) + "\n",
            encoding="utf-8",
        )
        return config_path

    @staticmethod
    def read_version(config_path: Path) -> str:
        return json.loads(config_path.read_text(encoding="utf-8"))["nerd_font"][
            "version"
        ]


if __name__ == "__main__":
    unittest.main()

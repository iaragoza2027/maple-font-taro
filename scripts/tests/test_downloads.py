from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.utils.downloads import (
    github_mirror_from_config,
    resolve_cached_download,
    resolve_download_url,
    validate_archive_path,
)


class DownloadUrlResolutionTest(unittest.TestCase):
    def test_resolves_github_release_through_mirror(self) -> None:
        url = "https://github.com/owner/repository/releases/download/v1/font.ttf"

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                resolve_download_url(url, "github.example.com"),
                "https://github.example.com/owner/repository/releases/download/v1/font.ttf",
            )

    def test_resolves_github_raw_url_through_mirror(self) -> None:
        url = "https://raw.githubusercontent.com/owner/repository/v1/font.ttf"

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                resolve_download_url(url, "github.example.com"),
                "https://github.example.com/owner/repository/raw/v1/font.ttf",
            )

    def test_normalizes_github_raw_url_without_mirror(self) -> None:
        url = "https://raw.githubusercontent.com/owner/repository/v1/font.ttf"

        with patch.dict(os.environ, {}, clear=True):
            resolved = resolve_download_url(url)

        self.assertEqual(
            resolved,
            "https://github.com/owner/repository/raw/v1/font.ttf",
        )

    def test_leaves_non_github_url_unchanged(self) -> None:
        url = "https://example.com/font.ttf"

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_download_url(url, "github.example.com"), url)

    def test_preserves_mirror_path_prefix(self) -> None:
        url = "https://github.com/owner/repository/releases/download/v1/font.ttf"

        with patch.dict(os.environ, {}, clear=True):
            resolved = resolve_download_url(
                url,
                "github.example.com/github.com",
            )

        self.assertEqual(
            resolved,
            "https://github.example.com/github.com/owner/repository/releases/download/v1/font.ttf",
        )

    def test_environment_mirror_overrides_configured_mirror(self) -> None:
        url = "https://github.com/owner/repository/releases/download/v1/font.ttf"

        with patch.dict(os.environ, {"GITHUB": "env.example.com"}):
            resolved = resolve_download_url(url, "config.example.com")

        self.assertEqual(
            resolved,
            "https://env.example.com/owner/repository/releases/download/v1/font.ttf",
        )

    def test_reads_task_mirror_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps({"github_mirror": "config.example.com"}),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    github_mirror_from_config(config_path),
                    "config.example.com",
                )


class CachedDownloadTest(unittest.TestCase):
    def test_missing_file_without_url_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "font.ttf"

            with self.assertRaisesRegex(FileNotFoundError, "font not found"):
                resolve_cached_download("font", target, None)


class ArchivePathValidationTest(unittest.TestCase):
    def test_accepts_relative_slash_separated_file_path(self) -> None:
        self.assertEqual(
            validate_archive_path("fonts/cjk/font.otf"),
            "fonts/cjk/font.otf",
        )

    def test_rejects_unsafe_or_ambiguous_paths(self) -> None:
        for path in ("", " font.otf", "/font.otf", "C:/font.otf", "a//b", "a/../b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_archive_path(path)


if __name__ == "__main__":
    unittest.main()

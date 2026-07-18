from __future__ import annotations

from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.utils.downloads import download_file


class FakeResponse:
    def __init__(self, payload: bytes, content_length: str | None) -> None:
        self._stream = BytesIO(payload)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self._stream.close()

    def read(self, size: int) -> bytes:
        return self._stream.read(size)


class DownloadProgressTest(unittest.TestCase):
    def test_reports_percentage_progress_on_one_terminal_line(self) -> None:
        payload = b"a" * 16384
        response = FakeResponse(payload, str(len(payload)))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "archive.zip"
            with (
                patch("scripts.utils.downloads.urlopen", return_value=response),
                patch("scripts.utils.downloads.log_progress") as progress,
            ):
                download_file("https://example.com/archive.zip", target)

            self.assertEqual(target.read_bytes(), payload)
            messages = [call.args[0] for call in progress.call_args_list]
            self.assertIn("archive.zip:   0%", messages[0])
            self.assertIn("archive.zip:  50%", messages[1])
            self.assertIn("archive.zip: 100%", messages[2])
            self.assertEqual(progress.call_args_list[-1].kwargs, {"complete": True})

    def test_skips_percentage_when_content_length_is_unavailable(self) -> None:
        for content_length in (None, "unknown"):
            with self.subTest(content_length=content_length):
                response = FakeResponse(b"font data", content_length)
                with tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / "font.ttf"
                    with (
                        patch("scripts.utils.downloads.urlopen", return_value=response),
                        patch("scripts.utils.downloads.log_progress") as progress,
                    ):
                        download_file("https://example.com/font.ttf", target)

                    progress.assert_not_called()


if __name__ == "__main__":
    unittest.main()

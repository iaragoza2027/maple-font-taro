from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.task import cjk_base


class CJKBaseTaskTest(unittest.TestCase):
    def test_missing_manifest_builds_all_locales(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                cjk_base.changed_locales(Path(tmp) / "missing.json"),
                ("cn", "jp", "tc", "kr"),
            )

    def test_changed_locales_only_returns_changed_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "locales": {
                            locale: {
                                "input_fingerprint": f"old-{locale}",
                                "static_sha256": "a" * 64,
                            }
                            for locale in ("cn", "jp", "tc", "kr")
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(
                    cjk_base,
                    "input_fingerprint",
                    side_effect=lambda locale: (
                        f"old-{locale}" if locale != "jp" else "new-jp"
                    ),
                ),
                patch.object(cjk_base, "_current_hash", return_value="a" * 64),
            ):
                self.assertEqual(cjk_base.changed_locales(manifest), ("jp",))

    def test_assemble_verify_and_render_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts" / "cn"
            artifacts.mkdir(parents=True)
            archive = artifacts / "cn-base-static.zip"
            with ZipFile(archive, "w") as zip_file:
                zip_file.writestr("MapleMonoCN-Regular.ttf", b"font")
            static_hash = "b" * 64
            (artifacts / "static-cn.sha256").write_text(
                f"{static_hash}\n", encoding="utf-8"
            )
            metadata = {
                "locale": "cn",
                "archive_name": archive.name,
                "archive_sha256": cjk_base._sha256(archive),
                "static_sha256": static_hash,
                "input_fingerprint": "input-cn",
                "source_url": "https://example.test/releases/download/v1/source.ttf",
                "source_ref": "v1",
                "built_at": "2026-08-02T00:00:00+00:00",
            }
            (artifacts / "metadata.json").write_text(
                json.dumps(metadata), encoding="utf-8"
            )
            baseline = root / "baseline.json"
            baseline.write_text(
                json.dumps({"schema": 1, "locales": {}}), encoding="utf-8"
            )
            candidate = root / "candidate"

            cjk_base.assemble_candidate(baseline, root / "artifacts", candidate)
            with (
                patch.object(cjk_base, "input_fingerprint", return_value="input-cn"),
                patch.object(
                    cjk_base, "_hash_path", return_value=root / "current.sha256"
                ),
            ):
                (root / "current.sha256").write_text(
                    f"{static_hash}\n", encoding="utf-8"
                )
                cjk_base.verify_candidate(candidate)

            notes = root / "notes.md"
            cjk_base.write_release_notes(candidate / "manifest.json", notes)
            content = notes.read_text(encoding="utf-8")
            self.assertIn("| CN | `v1` |", content)
            self.assertIn(
                "cn-base-static.zip",
                {path.name for path in (candidate / "assets").iterdir()},
            )

    def test_source_ref_supports_release_and_raw_urls(self) -> None:
        self.assertEqual(
            cjk_base.source_ref(
                "https://github.com/example/repo/releases/download/v1/font.ttf"
            ),
            "v1",
        )
        self.assertEqual(
            cjk_base.source_ref("https://github.com/example/repo/raw/v2/font.ttf"),
            "v2",
        )


if __name__ == "__main__":
    unittest.main()

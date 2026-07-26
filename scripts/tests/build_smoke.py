from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.font_ops.fonttools import TTFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ProductionBuildSmokeTest(unittest.TestCase):
    def test_debug_ttf_build_produces_readable_expected_fonts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp)
            (worktree / "config.json").symlink_to(PROJECT_ROOT / "config.json")
            (worktree / "source").symlink_to(
                PROJECT_ROOT / "source",
                target_is_directory=True,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "build.py"),
                    "--debug",
                    "--format",
                    "ttf",
                ],
                cwd=worktree,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"build stdout:\n{result.stdout}\nbuild stderr:\n{result.stderr}",
            )

            output_root = worktree / "fonts"
            variable_paths = sorted((output_root / "Variable").glob("*.ttf"))
            ttf_paths = sorted((output_root / "TTF").glob("*.ttf"))
            hinted_paths = sorted((output_root / "TTF-AutoHint").glob("*.ttf"))
            self.assertEqual(
                [path.name for path in variable_paths],
                [
                    "MapleMonoDebug-Italic[wght].ttf",
                    "MapleMonoDebug[wght].ttf",
                ],
            )
            self.assertEqual(
                [path.name for path in ttf_paths],
                ["MapleMonoDebug-Italic.ttf", "MapleMonoDebug-Regular.ttf"],
            )
            self.assertEqual(
                [path.name for path in hinted_paths],
                ["MapleMonoDebug-Italic.ttf", "MapleMonoDebug-Regular.ttf"],
            )
            self.assertFalse((output_root / "OTF").exists())
            self.assertFalse((output_root / "Woff2").exists())
            self.assertFalse((output_root / "NF").exists())

            for path in variable_paths:
                with self.subTest(path=path.name):
                    self.assert_font_metadata(path, variable=True)
            for path in ttf_paths:
                with self.subTest(path=path.relative_to(output_root)):
                    self.assert_font_metadata(path, variable=False)
            for path in hinted_paths:
                with self.subTest(path=path.relative_to(output_root)):
                    self.assert_font_metadata(path, variable=False, hinted=True)

    def assert_font_metadata(
        self,
        path: Path,
        *,
        variable: bool,
        hinted: bool = False,
    ) -> None:
        font = TTFont(path)
        try:
            self.assertIn("glyf", font)
            if variable:
                self.assertIn("fvar", font)
            else:
                self.assertNotIn("fvar", font)
            self.assertEqual(font["name"].getDebugName(1), "Maple Mono Debug")
            self.assertIn(font["name"].getDebugName(2), ("Regular", "Italic"))
            version = font["name"].getDebugName(5)
            if hinted:
                self.assertIsNotNone(version)
                self.assertTrue(version.startswith("Version 7.900; ttfautohint"))
            else:
                self.assertEqual(version, "Version 7.900")
        finally:
            font.close()


if __name__ == "__main__":
    unittest.main()

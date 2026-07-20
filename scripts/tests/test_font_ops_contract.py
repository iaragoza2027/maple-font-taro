from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FontOpsBoundaryTest(unittest.TestCase):
    def test_font_ops_does_not_load_cjk_or_build_runtime_modules(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import scripts.font_ops.fonttools, scripts.font_ops.glyph_transform, scripts.font_ops.glyphs, scripts.font_ops.merge, scripts.font_ops.metadata, scripts.font_ops.metrics, scripts.font_ops.names, scripts.font_ops.opentype, sys; assert 'glyphsLib' not in sys.modules; assert not any(name.startswith(('scripts.cjk', 'scripts.config', 'scripts.resolver')) for name in sys.modules)",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

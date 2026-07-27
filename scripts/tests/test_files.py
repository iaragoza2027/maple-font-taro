from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.utils.files import archive_fonts, archive_output_label


class FontArchiveTest(unittest.TestCase):
    def test_variable_output_labels_use_vf_suffix(self) -> None:
        self.assertEqual(archive_output_label("Variable"), "VF")
        self.assertEqual(archive_output_label("Variable-NF-CN"), "NF-CN-VF")
        self.assertEqual(archive_output_label("NF-CN"), "NF-CN")

    def test_archive_readme_links_only_relative_font_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Variable-NF-CN"
            source.mkdir()
            (source / "MapleMono-NF-CN[wght].ttf").write_bytes(b"font")
            (source / "README.md").write_text("stale", encoding="utf-8")
            config = root / "build-config.json"
            config.write_text("{}", encoding="utf-8")
            target = root / "archive"
            target.mkdir()

            _, name = archive_fonts(
                source_file_or_dir_path=str(source),
                target_parent_dir_path=str(target),
                family_name_compact="MapleMonoNR",
                suffix="",
                build_config_path=str(config),
            )

            self.assertEqual(name, "MapleMonoNR-NF-CN-VF")
            with ZipFile(target / f"{name}.zip") as archive:
                readme = archive.read("README.md").decode("utf-8")
                self.assertIn(
                    "[MapleMono-NF-CN[wght].ttf](./MapleMono-NF-CN%5Bwght%5D.ttf)",
                    readme,
                )
                self.assertNotIn("stale", readme)
                self.assertNotIn("config.json", archive.namelist())


if __name__ == "__main__":
    unittest.main()

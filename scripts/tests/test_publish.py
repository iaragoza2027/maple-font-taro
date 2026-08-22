from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.task.publish import (
    collect_release_task_archives,
    expected_release_archives,
    prepare_release_assets,
    release_build_steps,
    release_manifest,
    release_matrix,
    resolve_release_task,
)


class PublishTest(unittest.TestCase):
    def test_release_manifest_expands_complete_grouped_matrix(self) -> None:
        manifest = release_manifest()
        archives = expected_release_archives()

        self.assertIn("cjk", manifest)
        self.assertFalse(any(key.startswith("cjk_") for key in manifest))
        self.assertEqual(len(archives), 176)
        self.assertEqual(len(manifest["archives"]), 176)
        self.assertEqual(len(manifest["nf_variants"]), 3)
        self.assertFalse(any("NR" in name for name in archives))
        self.assertIn("MapleMonoSL-Woff2.zip", archives)
        self.assertFalse(
            any("Static" in name or "Variable" in name for name in archives)
        )
        self.assertFalse(any("NFMono-VF" in name for name in archives))
        self.assertFalse(any("NFPropo-VF" in name for name in archives))
        self.assertTrue(
            all(
                name.endswith("-NFMono-unhinted.zip") or "NFMono" not in name
                for name in archives
            )
        )
        self.assertTrue(
            all(
                name.endswith("-NFPropo-unhinted.zip") or "NFPropo" not in name
                for name in archives
            )
        )

    def test_prepare_release_assets_writes_manifest(self) -> None:
        expected = expected_release_archives()
        with tempfile.TemporaryDirectory() as tmp:
            release_dir = Path(tmp)
            for archive_name in expected:
                (release_dir / archive_name).write_bytes(archive_name.encode())

            prepare_release_assets(release_dir)

            self.assertTrue((release_dir / "release-manifest.json").is_file())
            self.assertFalse((release_dir / "SHA256SUMS").exists())
            self.assertFalse(list(release_dir.glob("*.sha256")))

    def test_release_matrix_exposes_eight_bundle_tasks(self) -> None:
        bundle = release_matrix()["task"]

        self.assertEqual(len(bundle), 8)
        self.assertFalse(any("narrow" in task for task in bundle))
        self.assertIn("bundle-normal-no-ligature-slim", bundle)

    def test_release_task_owns_build_steps_and_archive_names(self) -> None:
        with self.assertRaises(ValueError):
            resolve_release_task("base-normal-narrow")

        bundle = resolve_release_task("bundle-normal-slim")
        steps = release_build_steps(bundle, ("--least-styles",))
        self.assertEqual(len(steps), 8)
        self.assertTrue(all("--least-styles" in step.args for step in steps))
        self.assertIn("--hinted", steps[0].args)
        self.assertNotIn("--archive", steps[0].args)
        self.assertNotIn("--archive", steps[1].args)
        self.assertNotIn("--archive", steps[2].args)
        self.assertIn("--no-hinted", steps[1].args)
        self.assertIn("--nf-variable", steps[2].args)
        self.assertIn("--nf-mono", steps[3].args)
        self.assertIn("--nf-propo", steps[4].args)
        self.assertEqual(len(bundle.archive_names()), 22)
        self.assertIn("MapleMonoNormalSL-VF.zip", bundle.archive_names())
        self.assertIn("MapleMonoNormalSL-NF-VF.zip", bundle.archive_names())
        self.assertIn("MapleMonoNormalSL-NFMono-unhinted.zip", bundle.archive_names())
        self.assertIn("MapleMonoNormalSL-NFPropo-unhinted.zip", bundle.archive_names())
        self.assertIn("MapleMonoNormalSL-NF-JP-VF.zip", bundle.archive_names())
        self.assertIn("MapleMonoNormalSL-NF-KR-unhinted.zip", bundle.archive_names())

        cjk_steps = steps[5:]
        self.assertTrue(all("--cjk" in step.args for step in cjk_steps))
        self.assertTrue(all("cn,tc,jp,kr" in step.args for step in cjk_steps))
        self.assertIn("--hinted", cjk_steps[0].args)
        self.assertIn("--cache", cjk_steps[0].args)
        self.assertNotIn("--cjk-hinted", cjk_steps[0].args)
        self.assertIn("--cjk-variable", cjk_steps[2].args)
        self.assertEqual(
            {archive.directory for archive in cjk_steps[0].archives},
            {"NF-CN", "NF-TC", "NF-JP", "NF-KR"},
        )
        self.assertEqual(cjk_steps[1].archives[0].suffix, "-unhinted")
        self.assertEqual(
            {archive.directory for archive in cjk_steps[2].archives},
            {"Variable-NF-CN", "Variable-NF-TC", "Variable-NF-JP", "Variable-NF-KR"},
        )

    def test_collect_release_task_archives_isolates_job_outputs(self) -> None:
        task = resolve_release_task("bundle-default-default")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_dir = root / "archive"
            output_dir = root / "release-task"
            archive_dir.mkdir()
            for archive_name in task.archive_names():
                (archive_dir / archive_name).write_bytes(b"archive")
            (archive_dir / "MapleMono-TTF.zip").write_bytes(b"unrelated")

            collect_release_task_archives(task, archive_dir, output_dir)

            self.assertEqual(
                {path.name for path in output_dir.iterdir()},
                set(task.archive_names()),
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path

from scripts.pipeline.artifacts import _feature_fingerprint
from scripts.pipeline.cache import stage_identity
from scripts.utils.hashing import (
    hash_bytes,
    hash_directory,
    hash_file,
    hash_files,
    hash_json,
)


class HashingTest(unittest.TestCase):
    def test_bytes_and_file_use_standard_sha256(self) -> None:
        content = b"abc"
        expected = hashlib.sha256(content).hexdigest()

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "file.txt"
            path.write_bytes(content)

            self.assertEqual(hash_bytes(content), expected)
            self.assertEqual(hash_file(path), expected)

    def test_json_object_order_is_not_part_of_hash(self) -> None:
        first = hash_json({"first": 1, "second": 2})
        second = hash_json({"second": 2, "first": 1})

        self.assertEqual(first, second)

    def test_file_name_is_not_part_of_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "file.txt"
            path.write_text("abc", encoding="utf-8")

            self.assertEqual(hash_files({"a": path}), hash_files({"renamed": path}))

    def test_file_mapping_order_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_path = root / "first"
            second_path = root / "second"
            first_path.write_text("first", encoding="utf-8")
            second_path.write_text("second", encoding="utf-8")

            first = hash_files({"b": second_path, "a": first_path})
            second = hash_files({"a": first_path, "b": second_path})

            self.assertEqual(first, second)

    def test_file_boundaries_are_part_of_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_path = root / "first"
            second_path = root / "second"
            first_path.write_text("ab", encoding="utf-8")
            second_path.write_text("c", encoding="utf-8")
            first = hash_files({"a": first_path, "b": second_path})

            first_path.write_text("a", encoding="utf-8")
            second_path.write_text("bc", encoding="utf-8")

            self.assertNotEqual(first, hash_files({"a": first_path, "b": second_path}))

    def test_duplicate_file_contents_are_counted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_path = root / "first"
            second_path = root / "second"
            first_path.write_text("same", encoding="utf-8")
            second_path.write_text("same", encoding="utf-8")

            self.assertNotEqual(
                hash_files({"a": first_path}),
                hash_files({"a": first_path, "b": second_path}),
            )

    def test_filesystem_metadata_is_not_part_of_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "file.txt"
            path.write_text("abc", encoding="utf-8")
            first = hash_directory(root)

            stat_result = path.stat()
            os.utime(
                path,
                ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 1_000_000),
            )
            path.chmod(stat.S_IMODE(stat_result.st_mode) | stat.S_IXUSR)

            self.assertEqual(first, hash_directory(root))

    def test_symbolic_links_and_directories_are_not_file_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            target = Path(temporary) / "target.txt"
            target.write_text("content", encoding="utf-8")
            (root / "link.txt").symlink_to(target)

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                hash_directory(root)
            with self.assertRaisesRegex(ValueError, "regular file"):
                hash_file(root)

    def test_feature_fingerprint_does_not_include_file_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            features = root / "features"
            features.mkdir()
            feature = features / "a.fea"
            feature.write_text("feature liga { } liga;", encoding="utf-8")
            first = _feature_fingerprint(root)

            feature.rename(features / "renamed.fea")

            self.assertEqual(first, _feature_fingerprint(root))

    def test_stage_identity_is_order_independent_and_upstream_sensitive(self) -> None:
        first = stage_identity(
            {"first": 1, "second": 2},
            "stage",
            {"source": "a", "config": "b"},
        )
        second = stage_identity(
            {"second": 2, "first": 1},
            "stage",
            {"config": "b", "source": "a"},
        )
        changed = stage_identity(
            {"first": 1, "second": 2},
            "stage",
            {"source": "changed", "config": "b"},
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.pipeline.cache import (
    CACHE_SCHEMA,
    output_snapshot,
    read_cache_record,
    relative_cache_path,
    stage_identity,
    validate_stage,
    write_cache_record,
)


class PipelineCacheTest(unittest.TestCase):
    def test_record_uses_unix_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "TTF" / "MapleMono-Regular.ttf"
            output.parent.mkdir()
            output.write_bytes(b"font")

            files = output_snapshot(root, "ttf", [output])

            self.assertEqual(list(files), ["TTF/MapleMono-Regular.ttf"])
            self.assertNotIn("\\", next(iter(files)))

    def test_hash_mismatch_invalidates_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "Variable" / "MapleMono[wght].ttf"
            output.parent.mkdir()
            output.write_bytes(b"first")
            identity = stage_identity({"source": "one"}, "variable")
            record = {
                "schema": CACHE_SCHEMA,
                "identity": {"source": "one"},
                "stages": {
                    "variable": {
                        "identity": identity,
                        "files": output_snapshot(root, "variable", [output]),
                    }
                },
            }
            output.write_bytes(b"other")

            self.assertFalse(
                validate_stage(root, record, "variable", identity, [output])
            )

    def test_cache_record_is_written_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = {
                "schema": CACHE_SCHEMA,
                "identity": {},
                "stages": {},
            }

            write_cache_record(root, record)

            self.assertEqual(read_cache_record(root), record)
            self.assertFalse((root / ".build-cache.json.tmp").exists())

    def test_invalid_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build-cache.json").write_text(
                json.dumps({"schema": CACHE_SCHEMA + 1}),
                encoding="utf-8",
            )

            self.assertIsNone(read_cache_record(root))

    def test_cache_path_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fonts"
            root.mkdir()

            with self.assertRaises(ValueError):
                relative_cache_path(root, root / ".." / "outside.ttf")


if __name__ == "__main__":
    unittest.main()

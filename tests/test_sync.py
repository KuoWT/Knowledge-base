import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from knowledge_base_api.sync import stable_point_id, sync_repository


class SyncTests(unittest.TestCase):
    def test_stable_point_id_returns_uuid(self):
        point_id = stable_point_id("Meeting/2026/Meeting Index.md", "chunk-1")
        parsed = uuid.UUID(point_id)
        self.assertEqual(str(parsed), point_id)
        self.assertEqual(point_id, stable_point_id("Meeting/2026/Meeting Index.md", "chunk-1"))

    def test_sync_repository_deletes_before_upsert(self):
        class DummyStore:
            def __init__(self) -> None:
                self.values = {}

            def get_value(self, key):
                return self.values.get(key)

            def set_value(self, key, value):
                self.values[key] = value

            def list_index_record_ids_for_file(self, file_path):
                return ["old-point-1", "old-point-2"]

        class DummyWriter:
            def __init__(self) -> None:
                self.calls = []

            def delete(self, collection, ids):
                self.calls.append(("delete", collection, list(ids)))

            def upsert(self, collection, points):
                self.calls.append(("upsert", collection, [point.id for point in points]))

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "README.md").write_text("# Demo\n\nHello world.\n", encoding="utf-8")
            store = DummyStore()
            writer = DummyWriter()

            with patch("knowledge_base_api.sync.read_tracked_files", return_value=["README.md"]):
                result = sync_repository(
                    repo_path=repo_path,
                    store=store,
                    qdrant_writer=writer,
                    task_id="task_1",
                    commit_sha="abc123",
                    branch="master",
                    collection="knowledge_base",
                )

        self.assertEqual(writer.calls[0][0], "delete")
        self.assertEqual(writer.calls[1][0], "upsert")
        self.assertEqual(result["deleted"], 2)
        self.assertGreater(result["upserted"], 0)

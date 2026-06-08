import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from knowledge_base_api.sync import read_repo_markdown_files, read_tracked_files, stable_point_id, sync_repository


class SyncTests(unittest.TestCase):
    def test_read_repo_markdown_files_parses_null_separated_paths(self):
        class Result:
            returncode = 0
            stdout = "Meeting/2026/2026W01 週報摘要.md\0Project/index.md\0"
            stderr = ""

        with patch("knowledge_base_api.sync.run_git", return_value=Result()):
            files = read_repo_markdown_files(Path("/repo"))

        self.assertEqual(files, ["Meeting/2026/2026W01 週報摘要.md", "Project/index.md"])

    def test_read_tracked_files_parses_null_separated_diff_paths(self):
        class Result:
            def __init__(self, stdout="", returncode=0, stderr=""):
                self.stdout = stdout
                self.returncode = returncode
                self.stderr = stderr

        def fake_run_git(_repo_path, *args):
            if args[:2] == ("rev-parse", "--verify"):
                return Result(returncode=0, stdout="base-sha\n")
            if args[:1] == ("rev-parse",):
                return Result(returncode=0, stdout="head-sha\n")
            if args[:2] == ("diff", "--name-only"):
                return Result(returncode=0, stdout="README.md\0Project/index.md\0Meeting/2026/2026W01 週報摘要.md\0")
            raise AssertionError(args)

        with patch("knowledge_base_api.sync.run_git", side_effect=fake_run_git):
            files = read_tracked_files(Path("/repo"), "base-sha", "head-sha")

        self.assertEqual(
            files,
            ["README.md", "Project/index.md", "Meeting/2026/2026W01 週報摘要.md"],
        )

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

            with patch("knowledge_base_api.sync.resolve_commit_sha", return_value="abc123"), patch(
                "knowledge_base_api.sync.read_tracked_files", return_value=["README.md"]
            ):
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

    def test_sync_repository_full_rebuild_uses_repo_scan(self):
        class DummyStore:
            def __init__(self) -> None:
                self.values = {"last_synced_sha": "old-sha"}

            def get_value(self, key):
                return self.values.get(key)

            def set_value(self, key, value):
                self.values[key] = value

            def list_index_record_file_paths(self):
                return ["README.md", "old/Deleted.md"]

            def list_index_record_ids_for_file(self, file_path):
                mapping = {
                    "README.md": ["old-readme-1", "old-readme-2"],
                    "old/Deleted.md": ["old-deleted-1"],
                }
                return mapping.get(file_path, [])

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
            (repo_path / "Meeting.md").write_text("# Meeting\n\nNotes.\n", encoding="utf-8")
            store = DummyStore()
            writer = DummyWriter()

            with patch("knowledge_base_api.sync.resolve_commit_sha", return_value="abc123"), patch(
                "knowledge_base_api.sync.read_tracked_files", side_effect=AssertionError("should not diff")
            ), patch("knowledge_base_api.sync.read_repo_markdown_files", return_value=["README.md", "Meeting.md"]):
                result = sync_repository(
                    repo_path=repo_path,
                    store=store,
                    qdrant_writer=writer,
                    task_id="task_full",
                    commit_sha="abc123",
                    branch="master",
                    collection="knowledge_base",
                    full_repository=True,
                )

        self.assertEqual(result["mode"], "full_repository")
        self.assertEqual(result["changed_files"], ["README.md", "Meeting.md"])
        self.assertEqual(result["removed_files"], ["old/Deleted.md"])
        self.assertEqual(writer.calls[0][0], "delete")
        self.assertIn("old-readme-1", writer.calls[0][2])
        self.assertIn("old-deleted-1", writer.calls[1][2])
        self.assertEqual(writer.calls[-1][0], "upsert")
        self.assertEqual(store.get_value("last_synced_sha"), "abc123")

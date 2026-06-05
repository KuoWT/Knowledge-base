import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from knowledge_base_api.service import HermesService
from knowledge_base_api.store import Store


class StubWriter:
    def __init__(self) -> None:
        self.query_calls = []
        self.scroll_calls = []

    def query(self, collection, vector, limit, filters=None):
        self.query_calls.append(
            {
                "collection": collection,
                "vector": vector,
                "limit": limit,
                "filters": filters,
            }
        )
        return [
            {
                "id": "uuid-1",
                "score": 0.98,
                "payload": {
                    "file_path": "README.md",
                    "file_name": "README.md",
                    "chunk_id": "chunk-1",
                    "heading_path": "Intro",
                    "branch": "master",
                    "commit_sha": "abc123",
                    "content_hash": "hash",
                    "text": "hello world",
                    "text_preview": "hello world",
                },
            }
        ]

    def scroll(self, collection, limit, filters=None, order_by=None):
        self.scroll_calls.append(
            {
                "collection": collection,
                "limit": limit,
                "filters": filters,
                "order_by": order_by,
            }
        )
        return [
            {
                "id": "uuid-2",
                "payload": {
                    "file_path": "README.md",
                    "file_name": "README.md",
                    "chunk_id": "chunk-2",
                    "heading_path": "Intro / Sub",
                    "branch": "master",
                    "commit_sha": "abc123",
                    "content_hash": "hash2",
                    "text": "chunk content",
                    "text_preview": "chunk content",
                },
            }
        ]


class ServiceQueryTests(unittest.TestCase):
    def test_search_documents_uses_embedding_and_filters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "kb.db"
            store = Store(db_path)
            try:
                config = SimpleNamespace(
                    qdrant_url=None,
                    qdrant_api_key=None,
                    qdrant_collection="knowledge_base",
                    repo_path=Path(tmpdir),
                    main_branch="master",
                )
                service = HermesService(config, store)
                writer = StubWriter()
                service.qdrant_writer = lambda: writer  # type: ignore[assignment]

                result = service.search_documents("hello world", limit=99, file_path="README.md", branch="master")

                self.assertEqual(result["query"], "hello world")
                self.assertEqual(result["limit"], 1)
                self.assertEqual(result["items"][0]["file_path"], "README.md")
                self.assertEqual(writer.query_calls[0]["collection"], "knowledge_base")
                self.assertEqual(writer.query_calls[0]["limit"], 50)
                self.assertEqual(
                    writer.query_calls[0]["filters"],
                    {
                        "must": [
                            {"key": "file_path", "match": {"value": "README.md"}},
                            {"key": "branch", "match": {"value": "master"}},
                        ]
                    },
                )
            finally:
                store.close()

    def test_get_document_chunks_uses_scroll(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "kb.db"
            store = Store(db_path)
            try:
                config = SimpleNamespace(
                    qdrant_url=None,
                    qdrant_api_key=None,
                    qdrant_collection="knowledge_base",
                    repo_path=Path(tmpdir),
                    main_branch="master",
                )
                service = HermesService(config, store)
                writer = StubWriter()
                service.qdrant_writer = lambda: writer  # type: ignore[assignment]

                result = service.get_document_chunks("README.md", branch="master", limit=500)

                self.assertEqual(result["file_path"], "README.md")
                self.assertEqual(result["count"], 1)
                self.assertEqual(result["items"][0]["chunk_id"], "chunk-2")
                self.assertEqual(writer.scroll_calls[0]["limit"], 200)
                self.assertEqual(
                    writer.scroll_calls[0]["filters"],
                    {
                        "must": [
                            {"key": "file_path", "match": {"value": "README.md"}},
                            {"key": "branch", "match": {"value": "master"}},
                        ]
                    },
                )
                self.assertEqual(writer.scroll_calls[0]["order_by"], "position")
            finally:
                store.close()

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from knowledge_base_api.service import HermesService
from knowledge_base_api.store import Store


class QdrantBootstrapTests(unittest.TestCase):
    def test_ensure_qdrant_collection_bootstraps_when_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = Store(Path(tmpdir) / "kb.db")
            try:
                config = SimpleNamespace(
                    qdrant_url="http://example.test:6333",
                    qdrant_api_key=None,
                    qdrant_collection="knowledge_base",
                    repo_path=Path(tmpdir),
                    main_branch="master",
                )
                service = HermesService(config, store)
                calls = []

                class DummyWriter:
                    def ensure_collection(self, collection, vector_size):
                        calls.append((collection, vector_size))

                service.qdrant_writer = lambda: DummyWriter()  # type: ignore[assignment]
                service.ensure_qdrant_collection()

                self.assertEqual(calls, [("knowledge_base", 8)])
            finally:
                store.close()

    def test_ensure_qdrant_collection_skips_when_not_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = Store(Path(tmpdir) / "kb.db")
            try:
                config = SimpleNamespace(
                    qdrant_url=None,
                    qdrant_api_key=None,
                    qdrant_collection="knowledge_base",
                    repo_path=Path(tmpdir),
                    main_branch="master",
                )
                service = HermesService(config, store)

                class DummyWriter:
                    def ensure_collection(self, collection, vector_size):
                        raise AssertionError("should not be called")

                service.qdrant_writer = lambda: DummyWriter()  # type: ignore[assignment]
                service.ensure_qdrant_collection()
            finally:
                store.close()

import json
import unittest
from unittest.mock import patch

from knowledge_base_api.client import KnowledgeBaseClient


class DummyResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class KnowledgeBaseClientTests(unittest.TestCase):
    def test_search_builds_query_string(self):
        captured = {}

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["headers"] = dict(req.header_items())
            return DummyResponse({"items": []})

        client = KnowledgeBaseClient("http://localhost:8081", token="secret")
        with patch("knowledge_base_api.client.request.urlopen", side_effect=fake_urlopen):
            result = client.search("meeting index", limit=5, branch="master", file_path="README.md")

        self.assertEqual(result, {"items": []})
        self.assertEqual(
            captured["url"],
            "http://localhost:8081/api/v1/search?q=meeting+index&limit=5&branch=master&file_path=README.md",
        )
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["headers"].get("X-gitlab-token"), "secret")

    def test_submit_sync_task_sends_json_body(self):
        captured = {}

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["headers"] = dict(req.header_items())
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return DummyResponse({"task_id": "task_1", "status": "queued"})

        client = KnowledgeBaseClient("http://localhost:8081")
        with patch("knowledge_base_api.client.request.urlopen", side_effect=fake_urlopen):
            result = client.submit_sync_task(
                source="api",
                event_type="reindex",
                branch="master",
                commit_sha="abc123",
                trigger_reason="manual",
                paths=["README.md"],
            )

        self.assertEqual(result["status"], "queued")
        self.assertEqual(captured["url"], "http://localhost:8081/api/v1/sync-tasks")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["headers"].get("Content-type"), "application/json")
        self.assertEqual(captured["body"]["branch"], "master")
        self.assertEqual(captured["body"]["paths"], ["README.md"])

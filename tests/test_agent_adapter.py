import unittest
from unittest.mock import Mock

from knowledge_base_api.agent_adapter import KnowledgeBaseAdapter


class KnowledgeBaseAdapterTests(unittest.TestCase):
    def test_search_knowledge_base_defaults_to_master(self):
        client = Mock()
        client.search.return_value = {"items": []}
        adapter = KnowledgeBaseAdapter(client)

        result = adapter.search_knowledge_base("meeting index")

        self.assertEqual(result, {"items": []})
        client.search.assert_called_once_with("meeting index", limit=10, branch="master", file_path=None)

    def test_submit_update_request_forwards_arguments(self):
        client = Mock()
        client.submit_sync_task.return_value = {"task_id": "task_1", "status": "queued"}
        adapter = KnowledgeBaseAdapter(client)

        result = adapter.submit_update_request(
            source="api",
            event_type="reindex",
            project_id="27",
            branch="master",
            commit_sha="abc123",
            trigger_reason="manual",
            paths=["README.md"],
            full_repository=True,
        )

        self.assertEqual(result["status"], "queued")
        client.submit_sync_task.assert_called_once_with(
            source="api",
            event_type="reindex",
            project_id="27",
            branch="master",
            commit_sha="abc123",
            delivery_id=None,
            trigger_reason="manual",
            paths=["README.md"],
            full_repository=True,
        )

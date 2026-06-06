import io
import json
import unittest
from unittest.mock import Mock

from knowledge_base_api.mcp_server import KnowledgeBaseMCPServer, MCPWire


class DummyAdapter:
    def __init__(self) -> None:
        self.client = Mock()
        self.client.list_tasks.return_value = {"items": []}

    def health_check(self):
        return {"status": "ok", "service": "kb_api"}

    def ready_check(self):
        return {"status": "ok", "checks": {"db": True}}

    def search_knowledge_base(self, query, *, limit=10, branch="master", file_path=None):
        return {
            "query": query,
            "limit": limit,
            "branch": branch,
            "file_path": file_path,
            "items": [{"chunk_id": "chunk-1", "text": "hello"}],
        }

    def get_document(self, path, *, branch="master", limit=100):
        return {
            "path": path,
            "branch": branch,
            "limit": limit,
            "items": [
                {"chunk_id": "chunk-1", "text": "first", "position": 1},
                {"chunk_id": "chunk-2", "text": "second", "position": 2},
            ],
        }

    def get_task_status(self, task_id):
        return {"task_id": task_id, "status": "queued"}

    def submit_update_request(self, **kwargs):
        return {"task_id": "task_1", "status": "queued", "request": kwargs}

    def trigger_reindex(self, **kwargs):
        return {"task_id": "task_2", "status": "queued", "request": kwargs}


class MCPServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = KnowledgeBaseMCPServer(DummyAdapter())

    def test_initialize_returns_server_info(self):
        response = self.server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(response["result"]["serverInfo"]["name"], "knowledge-base-mcp")

    def test_tools_list_contains_expected_tools(self):
        response = self.server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertIn("search_knowledge_base", tool_names)
        self.assertIn("get_document", tool_names)
        self.assertIn("trigger_reindex", tool_names)

    def test_tools_call_search_routes_to_adapter(self):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "search_knowledge_base",
                    "arguments": {"query": "meeting index", "limit": 5, "branch": "master"},
                },
            }
        )
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["query"], "meeting index")
        self.assertEqual(payload["data"]["items"][0]["chunk_id"], "chunk-1")

    def test_tools_call_get_chunk_returns_single_item(self):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "get_chunk",
                    "arguments": {"file_path": "README.md", "chunk_id": "chunk-2"},
                },
            }
        )
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["chunk_id"], "chunk-2")
        self.assertEqual(payload["data"]["text"], "second")

    def test_tools_call_submit_update_request_routes_to_adapter(self):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "submit_update_request",
                    "arguments": {
                        "source": "api",
                        "event_type": "reindex",
                        "branch": "master",
                        "paths": ["README.md"],
                    },
                },
            }
        )
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "queued")
        self.assertEqual(payload["data"]["request"]["branch"], "master")

    def test_wire_supports_content_length_frames(self):
        request_payload = {"jsonrpc": "2.0", "id": 6, "method": "ping"}
        body = json.dumps(request_payload).encode("utf-8")
        reader = io.BytesIO(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body)
        writer = io.BytesIO()
        wire = MCPWire(reader, writer)

        self.assertEqual(wire.read_message(), request_payload)
        wire.write_message({"jsonrpc": "2.0", "id": 6, "result": {}})

        raw = writer.getvalue()
        header, payload = raw.split(b"\r\n\r\n", 1)
        self.assertTrue(header.startswith(b"Content-Length: "))
        self.assertEqual(json.loads(payload.decode("utf-8"))["id"], 6)


if __name__ == "__main__":
    unittest.main()

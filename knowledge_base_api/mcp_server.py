from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from io import BufferedReader, BufferedWriter
from typing import Any

from .agent_adapter import KnowledgeBaseAdapter
from .mcp_tools import MCP_PROTOCOL_VERSION, TOOL_INDEX, TOOLS


logger = logging.getLogger("kb_api.mcp")


@dataclass
class MCPConfig:
    base_url: str
    token: str | None
    timeout: int = 30


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _tool_wrapper(ok: bool, data: Any = None, error: dict[str, Any] | None = None, is_error: bool = False) -> dict[str, Any]:
    structured = {"ok": ok, "data": data, "error": error}
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": _json_dumps(structured)}],
        "structuredContent": structured,
    }
    if is_error:
        result["isError"] = True
    return result


class MCPWire:
    def __init__(self, reader: BufferedReader, writer: BufferedWriter) -> None:
        self.reader = reader
        self.writer = writer

    def read_message(self) -> dict[str, Any] | None:
        while True:
            first_line = self.reader.readline()
            if not first_line:
                return None
            stripped = first_line.strip()
            if not stripped:
                continue

            if stripped.startswith(b"{") or stripped.startswith(b"["):
                return json.loads(stripped.decode("utf-8"))

            headers: dict[str, str] = {}
            header_line = stripped
            while True:
                if b":" not in header_line:
                    logger.error("invalid MCP header line: %s", header_line.decode("utf-8", errors="replace"))
                    return None
                key, value = header_line.split(b":", 1)
                headers[key.decode("utf-8").strip().lower()] = value.decode("utf-8").strip()
                next_line = self.reader.readline()
                if not next_line:
                    return None
                if next_line in (b"\r\n", b"\n"):
                    break
                header_line = next_line.strip()

            content_length = headers.get("content-length")
            if content_length is None:
                logger.error("missing Content-Length header")
                return None
            try:
                length = int(content_length)
            except ValueError:
                logger.error("invalid Content-Length value: %s", content_length)
                return None
            body = self.reader.read(length)
            if not body:
                return None
            return json.loads(body.decode("utf-8"))

    def write_message(self, message: dict[str, Any]) -> None:
        raw = _json_dumps(message).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8")
        self.writer.write(header)
        self.writer.write(raw)
        self.writer.flush()


class KnowledgeBaseMCPServer:
    def __init__(self, adapter: KnowledgeBaseAdapter) -> None:
        self.adapter = adapter

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if message.get("method") == "notifications/initialized":
            return None
        if message.get("method") == "ping":
            return self._response(message.get("id"), {})
        if message.get("method") == "initialize":
            return self._response(
                message.get("id"),
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "serverInfo": {"name": "knowledge-base-mcp", "version": "0.1.0"},
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "logging": {},
                    },
                },
            )
        if message.get("method") == "tools/list":
            return self._response(message.get("id"), {"tools": TOOLS})
        if message.get("method") == "tools/call":
            return self._handle_tool_call(message)
        return self._error_response(message.get("id"), -32601, f"Method not found: {message.get('method')}")

    def _handle_tool_call(self, message: dict[str, Any]) -> dict[str, Any]:
        request_id = message.get("id")
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            return self._error_response(request_id, -32602, "Missing tool name")
        if name not in TOOL_INDEX:
            return self._error_response(request_id, -32601, f"Unknown tool: {name}")
        try:
            data = self._call_tool(name, arguments)
            return self._response(request_id, _tool_wrapper(ok=True, data=data))
        except ValueError as exc:
            return self._response(
                request_id,
                _tool_wrapper(
                    ok=False,
                    error={"code": "invalid_params", "message": str(exc)},
                    is_error=True,
                ),
            )
        except KeyError as exc:
            return self._response(
                request_id,
                _tool_wrapper(
                    ok=False,
                    error={"code": "not_found", "message": str(exc)},
                    is_error=True,
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("mcp tool failed name=%s", name)
            return self._response(
                request_id,
                _tool_wrapper(
                    ok=False,
                    error={"code": "internal_error", "message": str(exc)},
                    is_error=True,
                ),
            )

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "health_check":
            return self.adapter.health_check()
        if name == "ready_check":
            return self.adapter.ready_check()
        if name == "search_knowledge_base":
            return self.adapter.search_knowledge_base(
                arguments["query"],
                limit=int(arguments.get("limit", 10)),
                branch=arguments.get("branch") or "master",
                file_path=arguments.get("file_path"),
            )
        if name == "get_document":
            return self.adapter.get_document(
                arguments["path"],
                branch=arguments.get("branch") or "master",
                limit=int(arguments.get("limit", 100)),
            )
        if name == "get_chunk":
            document = self.adapter.get_document(
                arguments["file_path"],
                branch=arguments.get("branch") or "master",
                limit=500,
            )
            chunk_id = arguments["chunk_id"]
            for item in document.get("items", []):
                if item.get("chunk_id") == chunk_id:
                    return item
            raise KeyError(f"chunk not found: {chunk_id}")
        if name == "get_document_sources":
            document = self.adapter.get_document(
                arguments["path"],
                branch=arguments.get("branch") or "master",
                limit=500,
            )
            items = document.get("items", [])
            if not items:
                return {"file_path": arguments["path"], "count": 0, "items": []}
            first = items[0]
            return {
                "file_path": arguments["path"],
                "branch": first.get("branch"),
                "commit_sha": first.get("commit_sha"),
                "content_hash": first.get("content_hash"),
                "count": len(items),
                "chunk_ids": [item.get("chunk_id") for item in items],
                "headings": [item.get("heading_path") for item in items],
            }
        if name == "get_task_status":
            return self.adapter.get_task_status(arguments["task_id"])
        if name == "list_tasks":
            return self.adapter.client.list_tasks(
                status=arguments.get("status"),
                source=arguments.get("source"),
            )
        if name == "submit_update_request":
            return self.adapter.submit_update_request(
                source=arguments.get("source", "api"),
                event_type=arguments.get("event_type"),
                project_id=arguments.get("project_id"),
                branch=arguments.get("branch") or "master",
                commit_sha=arguments.get("commit_sha"),
                delivery_id=arguments.get("delivery_id"),
                trigger_reason=arguments.get("trigger_reason"),
                paths=arguments.get("paths") or [],
                full_repository=bool(arguments.get("full_repository", False)),
            )
        if name == "trigger_reindex":
            return self.adapter.trigger_reindex(
                branch=arguments.get("branch") or "master",
                project_id=arguments.get("project_id"),
                commit_sha=arguments.get("commit_sha"),
                delivery_id=arguments.get("delivery_id"),
                reason=arguments.get("reason"),
                paths=arguments.get("paths") or [],
                scope=arguments.get("scope"),
            )
        raise KeyError(name)

    def _response(self, request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        return response

    def _error_response(self, request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}


def run_stdio_server() -> None:
    log_level = os.getenv("KB_API_MCP_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    base_url = os.getenv("KB_API_BASE_URL", "http://localhost:8081")
    token = os.getenv("KB_API_WEBHOOK_TOKEN") or None
    timeout = int(os.getenv("KB_API_HTTP_TIMEOUT", "30"))
    adapter = KnowledgeBaseAdapter.from_url(base_url, token=token, timeout=timeout)
    server = KnowledgeBaseMCPServer(adapter)
    wire = MCPWire(sys.stdin.buffer, sys.stdout.buffer)

    while True:
        try:
            message = wire.read_message()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error("invalid json received: %s", exc)
            continue
        if message is None:
            break
        if not isinstance(message, dict):
            logger.error("invalid MCP message type: %s", type(message).__name__)
            continue
        if message.get("jsonrpc") not in (None, "2.0"):
            logger.error("unsupported jsonrpc version: %s", message.get("jsonrpc"))
            continue
        response = server.handle_message(message)
        if response is None:
            continue
        wire.write_message(response)


def main() -> None:
    run_stdio_server()


if __name__ == "__main__":
    main()

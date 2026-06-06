from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


@dataclass
class MCPResponse:
    raw: dict[str, Any]

    @property
    def result(self) -> dict[str, Any]:
        return self.raw.get("result") or {}

    @property
    def error(self) -> dict[str, Any] | None:
        return self.raw.get("error")


class StdioMCPClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self.command = command
        self.env = env or {}
        self.proc: subprocess.Popen[bytes] | None = None
        self._next_id = 1

    def __enter__(self) -> "StdioMCPClient":
        merged_env = os.environ.copy()
        merged_env.update(self.env)
        self.proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            env=merged_env,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()

    def request(self, method: str, params: dict[str, Any] | None = None) -> MCPResponse:
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("MCP client is not running")
        request_id = self._next_id
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)
        return MCPResponse(self._read())

    def _write(self, message: dict[str, Any]) -> None:
        assert self.proc is not None and self.proc.stdin is not None
        payload = _json_dumps(message).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8")
        self.proc.stdin.write(header + payload)
        self.proc.stdin.flush()

    def _read(self) -> dict[str, Any]:
        assert self.proc is not None and self.proc.stdout is not None
        headers: dict[str, str] = {}
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed stdout")
            if line in (b"\r\n", b"\n"):
                break
            stripped = line.strip()
            if not stripped:
                continue
            if b":" not in stripped:
                raise RuntimeError(f"Invalid MCP header line: {stripped!r}")
            key, value = stripped.split(b":", 1)
            headers[key.decode("utf-8").lower()] = value.decode("utf-8").strip()
        content_length = int(headers.get("content-length", "0"))
        payload = self.proc.stdout.read(content_length)
        if payload is None:
            raise RuntimeError("MCP server returned no payload")
        return json.loads(payload.decode("utf-8"))


def run_example() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    server_command = [sys.executable, "-m", "knowledge_base_api.mcp_server"]
    env = {
        "KB_API_BASE_URL": os.getenv("KB_API_BASE_URL", "http://localhost:8081"),
        "KB_API_WEBHOOK_TOKEN": os.getenv("KB_API_WEBHOOK_TOKEN", ""),
        "KB_API_HTTP_TIMEOUT": os.getenv("KB_API_HTTP_TIMEOUT", "30"),
        "KB_API_MCP_LOG_LEVEL": os.getenv("KB_API_MCP_LOG_LEVEL", "INFO"),
        "PYTHONPATH": str(repo_root),
    }

    with StdioMCPClient(server_command, env=env) as client:
        initialize = client.request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "clientInfo": {"name": "hermes-agent-example", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )
        print("INITIALIZE:", json.dumps(initialize.raw, ensure_ascii=False, indent=2))

        tools = client.request("tools/list")
        print("TOOLS:", json.dumps(tools.raw, ensure_ascii=False, indent=2))

        search = client.request(
            "tools/call",
            {
                "name": "search_knowledge_base",
                "arguments": {"query": "README", "limit": 5, "branch": "master"},
            },
        )
        print("SEARCH:", json.dumps(search.raw, ensure_ascii=False, indent=2))

        document = client.request(
            "tools/call",
            {
                "name": "get_document",
                "arguments": {"path": "README.md", "branch": "master"},
            },
        )
        print("DOCUMENT:", json.dumps(document.raw, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_example()

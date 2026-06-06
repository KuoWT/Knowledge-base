from __future__ import annotations

from typing import Any


MCP_PROTOCOL_VERSION = "2025-11-25"


def _object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _tool_result_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "data": {
                "anyOf": [
                    {"type": "object"},
                    {"type": "array"},
                    {"type": "string"},
                    {"type": "number"},
                    {"type": "boolean"},
                    {"type": "null"},
                ]
            },
            "error": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                            "details": {},
                        },
                        "required": ["code", "message"],
                    },
                ]
            },
        },
        "required": ["ok", "data", "error"],
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "health_check",
        "description": "Check service liveness.",
        "inputSchema": _object_schema(
            {
                "detail": {"type": "boolean", "default": False},
            }
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "ready_check",
        "description": "Check whether the API, repo, git, and Qdrant dependencies are ready.",
        "inputSchema": _object_schema(
            {
                "detail": {"type": "boolean", "default": False},
            }
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "search_knowledge_base",
        "description": "Search indexed Markdown chunks in the knowledge base.",
        "inputSchema": _object_schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "default": 10},
                "branch": {"type": "string", "default": "master"},
                "file_path": {"type": "string"},
            },
            required=["query"],
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_document",
        "description": "Return all indexed chunks for a Markdown file in original order.",
        "inputSchema": _object_schema(
            {
                "path": {"type": "string"},
                "branch": {"type": "string", "default": "master"},
                "limit": {"type": "integer", "minimum": 1, "default": 100},
            },
            required=["path"],
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_chunk",
        "description": "Return a single chunk from a Markdown file by chunk id.",
        "inputSchema": _object_schema(
            {
                "file_path": {"type": "string"},
                "chunk_id": {"type": "string"},
                "branch": {"type": "string", "default": "master"},
            },
            required=["file_path", "chunk_id"],
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_document_sources",
        "description": "Return source metadata and chunk summary for a Markdown file.",
        "inputSchema": _object_schema(
            {
                "path": {"type": "string"},
                "branch": {"type": "string", "default": "master"},
            },
            required=["path"],
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_task_status",
        "description": "Return a sync task status by task id.",
        "inputSchema": _object_schema(
            {
                "task_id": {"type": "string"},
            },
            required=["task_id"],
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_tasks",
        "description": "List sync tasks with optional filters.",
        "inputSchema": _object_schema(
            {
                "status": {"type": "string"},
                "source": {"type": "string"},
            }
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "submit_update_request",
        "description": "Create a new sync task request.",
        "inputSchema": _object_schema(
            {
                "source": {"type": "string", "default": "api"},
                "event_type": {"type": "string"},
                "project_id": {"type": "string"},
                "branch": {"type": "string", "default": "master"},
                "commit_sha": {"type": "string"},
                "delivery_id": {"type": "string"},
                "trigger_reason": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}, "default": []},
                "full_repository": {"type": "boolean", "default": False},
            }
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "trigger_reindex",
        "description": "Trigger a repository or path-based reindex task.",
        "inputSchema": _object_schema(
            {
                "branch": {"type": "string", "default": "master"},
                "project_id": {"type": "string"},
                "commit_sha": {"type": "string"},
                "delivery_id": {"type": "string"},
                "reason": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}, "default": []},
                "scope": {"type": "string", "enum": ["repository", "paths"]},
            }
        ),
        "outputSchema": _tool_result_schema(),
        "annotations": {"readOnlyHint": False},
    },
]


TOOL_INDEX = {tool["name"]: tool for tool in TOOLS}

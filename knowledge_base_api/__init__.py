"""Knowledge base API service."""

from __future__ import annotations

from .agent_adapter import KnowledgeBaseAdapter
from .client import KnowledgeBaseClient

__all__ = ["KnowledgeBaseClient", "KnowledgeBaseAdapter", "KnowledgeBaseMCPServer", "run_mcp_server"]


def __getattr__(name: str):
    if name in {"KnowledgeBaseMCPServer", "run_mcp_server"}:
        from .mcp_server import KnowledgeBaseMCPServer, main as run_mcp_server

        return {"KnowledgeBaseMCPServer": KnowledgeBaseMCPServer, "run_mcp_server": run_mcp_server}[name]
    raise AttributeError(name)

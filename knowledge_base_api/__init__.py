"""Knowledge base API service."""

from .agent_adapter import KnowledgeBaseAdapter
from .client import KnowledgeBaseClient
from .mcp_server import KnowledgeBaseMCPServer, main as run_mcp_server

__all__ = ["KnowledgeBaseClient", "KnowledgeBaseAdapter", "KnowledgeBaseMCPServer", "run_mcp_server"]

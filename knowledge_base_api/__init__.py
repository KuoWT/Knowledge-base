"""Knowledge base API service."""

from .agent_adapter import KnowledgeBaseAdapter
from .client import KnowledgeBaseClient

__all__ = ["KnowledgeBaseClient", "KnowledgeBaseAdapter"]

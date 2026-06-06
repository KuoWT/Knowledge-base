from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import KnowledgeBaseClient


@dataclass(frozen=True)
class KnowledgeBaseAdapter:
    client: KnowledgeBaseClient

    @classmethod
    def from_url(
        cls,
        base_url: str,
        *,
        token: str | None = None,
        timeout: int = 30,
    ) -> "KnowledgeBaseAdapter":
        return cls(KnowledgeBaseClient(base_url, token=token, timeout=timeout))

    def search_knowledge_base(
        self,
        query: str,
        *,
        limit: int = 10,
        branch: str | None = "master",
        file_path: str | None = None,
    ) -> dict[str, Any]:
        return self.client.search(query, limit=limit, branch=branch, file_path=file_path)

    def get_document(
        self,
        path: str,
        *,
        branch: str | None = "master",
        limit: int = 100,
    ) -> dict[str, Any]:
        return self.client.get_document(path, branch=branch, limit=limit)

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        return self.client.get_task(task_id)

    def health_check(self) -> dict[str, Any]:
        return self.client.health_check()

    def ready_check(self) -> dict[str, Any]:
        return self.client.ready_check()

    def submit_update_request(
        self,
        *,
        source: str = "api",
        event_type: str | None = None,
        project_id: str | None = None,
        branch: str | None = "master",
        commit_sha: str | None = None,
        delivery_id: str | None = None,
        trigger_reason: str | None = None,
        paths: list[str] | None = None,
        full_repository: bool = False,
    ) -> dict[str, Any]:
        return self.client.submit_sync_task(
            source=source,
            event_type=event_type,
            project_id=project_id,
            branch=branch,
            commit_sha=commit_sha,
            delivery_id=delivery_id,
            trigger_reason=trigger_reason,
            paths=paths,
            full_repository=full_repository,
        )

    def trigger_reindex(
        self,
        *,
        branch: str | None = "master",
        project_id: str | None = None,
        commit_sha: str | None = None,
        delivery_id: str | None = None,
        reason: str | None = None,
        paths: list[str] | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        return self.client.reindex(
            branch=branch,
            project_id=project_id,
            commit_sha=commit_sha,
            delivery_id=delivery_id,
            reason=reason,
            paths=paths,
            scope=scope,
        )

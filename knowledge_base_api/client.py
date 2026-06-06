from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import parse, request


@dataclass(frozen=True)
class KnowledgeBaseClient:
    base_url: str
    token: str | None = None
    timeout: int = 30

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        branch: str | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        params = {"q": query, "limit": str(limit)}
        if branch:
            params["branch"] = branch
        if file_path:
            params["file_path"] = file_path
        return self._get("/api/v1/search", params)

    def get_document(
        self,
        path: str,
        *,
        branch: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        params = {"path": path, "limit": str(limit)}
        if branch:
            params["branch"] = branch
        return self._get("/api/v1/documents", params)

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/sync-tasks/{parse.quote(task_id, safe='')}")

    def health_check(self) -> dict[str, Any]:
        return self._get("/health")

    def ready_check(self) -> dict[str, Any]:
        return self._get("/ready")

    def list_tasks(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if source:
            params["source"] = source
        return self._get("/api/v1/sync-tasks", params or None)

    def submit_sync_task(
        self,
        *,
        source: str = "api",
        event_type: str | None = None,
        project_id: str | None = None,
        branch: str | None = None,
        commit_sha: str | None = None,
        delivery_id: str | None = None,
        trigger_reason: str | None = None,
        paths: list[str] | None = None,
        full_repository: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": source,
            "event_type": event_type,
            "project_id": project_id,
            "branch": branch,
            "commit_sha": commit_sha,
            "delivery_id": delivery_id,
            "trigger_reason": trigger_reason,
            "paths": paths or [],
            "full_repository": full_repository,
        }
        return self._post("/api/v1/sync-tasks", payload)

    def reindex(
        self,
        *,
        branch: str | None = None,
        project_id: str | None = None,
        commit_sha: str | None = None,
        delivery_id: str | None = None,
        reason: str | None = None,
        paths: list[str] | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "branch": branch,
            "project_id": project_id,
            "commit_sha": commit_sha,
            "delivery_id": delivery_id,
            "reason": reason,
            "paths": paths or [],
            "scope": scope,
        }
        return self._post("/api/v1/reindex", payload)

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        url = self.base_url + path
        if params:
            query = parse.urlencode({key: value for key, value in params.items() if value is not None})
            if query:
                url = f"{url}?{query}"
        return self._request("GET", url, None)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", self.base_url + path, payload)

    def _request(self, method: str, url: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Gitlab-Token"] = self.token
        req = request.Request(url, data=body, headers=headers, method=method)
        with request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

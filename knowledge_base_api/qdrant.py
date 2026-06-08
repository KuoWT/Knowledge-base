from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any
from urllib import error, request


logger = logging.getLogger("kb_api.qdrant")


@dataclass
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class QdrantWriter:
    def ensure_collection(self, collection: str, vector_size: int) -> None:
        raise NotImplementedError

    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        raise NotImplementedError

    def delete(self, collection: str, ids: list[str]) -> None:
        raise NotImplementedError

    def query(
        self,
        collection: str,
        vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def scroll(
        self,
        collection: str,
        limit: int,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


class LocalQdrantWriter(QdrantWriter):
    def __init__(self) -> None:
        pass

    def ensure_collection(self, collection: str, vector_size: int) -> None:
        return None

    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        return None

    def delete(self, collection: str, ids: list[str]) -> None:
        # Local adapter records no-op deletes; the task log still reflects the operation.
        return None

    def query(
        self,
        collection: str,
        vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return []

    def scroll(
        self,
        collection: str,
        limit: int,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        return []


class HttpQdrantWriter(QdrantWriter):
    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._ready_collections: set[str] = set()

    def ensure_collection(self, collection: str, vector_size: int) -> None:
        if collection in self._ready_collections:
            return
        if self._collection_exists(collection):
            self._ready_collections.add(collection)
            return
        payload = {
            "vectors": {
                "size": vector_size,
                "distance": "Cosine",
            }
        }
        self._request("PUT", f"/collections/{collection}", payload)
        self._ready_collections.add(collection)

    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        if not points:
            return
        self.ensure_collection(collection, len(points[0].vector))
        payload = {
            "points": [point.to_json() for point in points],
        }
        self._request("PUT", f"/collections/{collection}/points?wait=true", payload)

    def delete(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        payload = {"points": ids}
        self._request("POST", f"/collections/{collection}/points/delete?wait=true", payload)

    def query(
        self,
        collection: str,
        vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "query": vector,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        if filters:
            payload["filter"] = filters
        response = self._request("POST", f"/collections/{collection}/points/query", payload)
        if not response:
            return []
        return self._extract_points(response)

    def scroll(
        self,
        collection: str,
        limit: int,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        if filters:
            payload["filter"] = filters
        if order_by:
            payload["order_by"] = order_by
        response = self._request("POST", f"/collections/{collection}/points/scroll", payload)
        if not response:
            return []
        return self._extract_points(response)

    def _extract_points(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        result = response.get("result")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            points = result.get("points")
            if isinstance(points, list):
                return [item for item in points if isinstance(item, dict)]
            if isinstance(result.get("point"), dict):
                return [result["point"]]
        if result is not None:
            logger.warning("unexpected qdrant response shape result_type=%s keys=%s", type(result).__name__, list(response.keys()))
        return []

    def _collection_exists(self, collection: str) -> bool:
        try:
            self._request("GET", f"/collections/{collection}", None)
            return True
        except error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def _request(self, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any] | None:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        req = request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            if not body:
                return None
            return json.loads(body.decode("utf-8"))


class NoopQdrantWriter(QdrantWriter):
    def ensure_collection(self, collection: str, vector_size: int) -> None:
        return None

    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        return None

    def delete(self, collection: str, ids: list[str]) -> None:
        return None

    def query(
        self,
        collection: str,
        vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return []

    def scroll(
        self,
        collection: str,
        limit: int,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

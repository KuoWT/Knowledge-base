from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any
from urllib import error, request


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

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any
from urllib import request


@dataclass
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class QdrantWriter:
    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        raise NotImplementedError

    def delete(self, collection: str, ids: list[str]) -> None:
        raise NotImplementedError


class LocalQdrantWriter(QdrantWriter):
    def __init__(self) -> None:
        pass

    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        return None

    def delete(self, collection: str, ids: list[str]) -> None:
        # Local adapter records no-op deletes; the task log still reflects the operation.
        return None


class HttpQdrantWriter(QdrantWriter):
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        payload = {
            "wait": True,
            "points": [point.to_json() for point in points],
        }
        self._post(f"/collections/{collection}/points?wait=true", payload)

    def delete(self, collection: str, ids: list[str]) -> None:
        payload = {"points": ids}
        self._post(f"/collections/{collection}/points/delete?wait=true", payload)

    def _post(self, path: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=30) as resp:
            resp.read()


class NoopQdrantWriter(QdrantWriter):
    def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        return None

    def delete(self, collection: str, ids: list[str]) -> None:
        return None

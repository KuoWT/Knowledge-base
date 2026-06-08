from __future__ import annotations

import logging
import queue
import threading
import uuid
from typing import Any

from .qdrant import HttpQdrantWriter, LocalQdrantWriter
from .store import Store, utcnow_iso
from .sync import pseudo_embedding, run_git, sync_repository


logger = logging.getLogger("kb_api.service")


class HermesService:
    def __init__(self, config, store: Store) -> None:
        self.config = config
        self.store = store
        self.queue: queue.Queue[str] = queue.Queue()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def qdrant_writer(self):
        if self.config.qdrant_url:
            return HttpQdrantWriter(self.config.qdrant_url, api_key=self.config.qdrant_api_key)
        return LocalQdrantWriter()

    def ensure_qdrant_collection(self) -> None:
        if not self.config.qdrant_url:
            logger.info("qdrant not configured; skip collection bootstrap")
            return
        writer = self.qdrant_writer()
        vector_size = len(pseudo_embedding("__qdrant_bootstrap__"))
        writer.ensure_collection(self.config.qdrant_collection, vector_size)
        logger.info(
            "qdrant collection ready collection=%s vector_size=%s",
            self.config.qdrant_collection,
            vector_size,
        )

    def _qdrant_filter(
        self,
        *,
        file_path: str | None = None,
        branch: str | None = None,
    ) -> dict[str, Any] | None:
        must: list[dict[str, Any]] = []
        if file_path:
            must.append({"key": "file_path", "match": {"value": file_path}})
        if branch:
            must.append({"key": "branch", "match": {"value": branch}})
        if not must:
            return None
        return {"must": must}

    def enqueue_sync(
        self,
        source: str,
        event_type: str | None,
        project_id: str | None,
        branch: str | None,
        commit_sha: str | None,
        delivery_id: str | None,
        trigger_reason: str | None,
        paths: list[str] | None = None,
        full_repository: bool = False,
    ):
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = self.store.create_task(
            task_id=task_id,
            status="queued",
            source=source,
            event_type=event_type,
            project_id=project_id,
            branch=branch,
            commit_sha=commit_sha,
            delivery_id=delivery_id,
            trigger_reason=trigger_reason,
        )
        self.store.conn.execute(
            "UPDATE sync_tasks SET error = ? WHERE task_id = ?",
            (None, task_id),
        )
        self.store.conn.commit()
        logger.info(
            "task queued task_id=%s source=%s event_type=%s branch=%s commit_sha=%s trigger_reason=%s",
            task_id,
            source,
            event_type,
            branch,
            commit_sha,
            trigger_reason,
        )
        self.queue.put(
            self._serialize_job(
                task_id=task_id,
                commit_sha=commit_sha,
                branch=branch or self.config.main_branch,
                paths=paths or [],
                full_repository=full_repository,
            )
        )
        return task

    def retry_task(self, task_id: str):
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        self.store.update_task(task_id, status="retrying")
        logger.info("task retrying task_id=%s source=%s", task_id, task.source)
        self.queue.put(self._serialize_job(task_id=task_id, commit_sha=task.commit_sha, branch=task.branch or self.config.main_branch, paths=[], full_repository=False))
        return self.store.get_task(task_id)

    def _serialize_job(self, **kwargs: Any) -> str:
        import json

        return json.dumps(kwargs, ensure_ascii=False)

    def _deserialize_job(self, payload: str) -> dict[str, Any]:
        import json

        return json.loads(payload)

    def _worker_loop(self) -> None:
        while True:
            payload = self.queue.get()
            job = self._deserialize_job(payload)
            task_id = job["task_id"]
            try:
                logger.info("task started task_id=%s source=%s", task_id, self.store.get_task(task_id).source)
                self.store.update_task(task_id, status="running", started_at=utcnow_iso())
                self._process_task(job)
                self.store.update_task(task_id, status="succeeded", finished_at=utcnow_iso(), error=None)
                logger.info("task succeeded task_id=%s", task_id)
            except Exception as exc:  # pragma: no cover - defensive
                self.store.update_task(task_id, status="failed", finished_at=utcnow_iso(), error=str(exc))
                logger.exception("task failed task_id=%s error=%s", task_id, exc)
            finally:
                self.queue.task_done()

    def _process_task(self, job: dict[str, Any]) -> None:
        task_id = job["task_id"]
        commit_sha = job.get("commit_sha")
        branch = job.get("branch") or self.config.main_branch
        full_repository = bool(job.get("full_repository", False))
        paths = job.get("paths") or []
        result = run_git(self.config.repo_path, "pull", "--ff-only")
        if result.returncode != 0:
            logger.error("git pull failed task_id=%s stderr=%s", task_id, result.stderr.strip())
            raise RuntimeError(result.stderr.strip() or "git pull failed")
        logger.info(
            "git pull ok task_id=%s branch=%s full_repository=%s paths=%s",
            task_id,
            branch,
            full_repository,
            paths,
        )
        writer = self.qdrant_writer()
        result = sync_repository(
            repo_path=self.config.repo_path,
            store=self.store,
            qdrant_writer=writer,
            task_id=task_id,
            commit_sha=commit_sha,
            branch=branch,
            collection=self.config.qdrant_collection,
            full_repository=full_repository,
            paths=paths,
        )
        logger.info(
            "sync completed task_id=%s mode=%s changed_files=%s removed_files=%s upserted=%s deleted=%s",
            task_id,
            result.get("mode"),
            len(result.get("changed_files", [])),
            len(result.get("removed_files", [])),
            result.get("upserted"),
            result.get("deleted"),
        )
        for rel_path in result.get("changed_files", []):
            self.store.delete_index_records_for_file(rel_path)
        for rel_path in result.get("removed_files", []):
            self.store.delete_index_records_for_file(rel_path)
        for point in result.get("points", []):
            self.store.add_index_record(
                task_id=task_id,
                file_path=point.payload["file_path"],
                chunk_id=point.id,
                payload={"collection": self.config.qdrant_collection, **point.to_json()},
            )

    def search_documents(
        self,
        query_text: str,
        *,
        limit: int = 10,
        file_path: str | None = None,
        branch: str | None = None,
    ) -> dict[str, Any]:
        query_text = query_text.strip()
        if not query_text:
            raise ValueError("query_text is required")
        writer = self.qdrant_writer()
        results = writer.query(
            self.config.qdrant_collection,
            pseudo_embedding(query_text),
            max(1, min(limit, 50)),
            filters=self._qdrant_filter(file_path=file_path, branch=branch),
        )
        items: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                logger.warning("unexpected qdrant query item type=%s value=%r", type(item).__name__, item)
                continue
            payload = item.get("payload") or {}
            items.append(
                {
                    "id": item.get("id"),
                    "score": item.get("score"),
                    "file_path": payload.get("file_path"),
                    "file_name": payload.get("file_name"),
                    "chunk_id": payload.get("chunk_id"),
                    "heading_path": payload.get("heading_path"),
                    "position": payload.get("position"),
                    "branch": payload.get("branch"),
                    "commit_sha": payload.get("commit_sha"),
                    "content_hash": payload.get("content_hash"),
                    "text": payload.get("text"),
                    "text_preview": payload.get("text_preview"),
                    "payload": payload,
                }
            )
        return {
            "query": query_text,
            "limit": len(items),
            "items": items,
        }

    def get_document_chunks(
        self,
        file_path: str,
        *,
        branch: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        file_path = file_path.strip()
        if not file_path:
            raise ValueError("file_path is required")
        writer = self.qdrant_writer()
        results = writer.scroll(
            self.config.qdrant_collection,
            max(1, min(limit, 200)),
            filters=self._qdrant_filter(file_path=file_path, branch=branch),
            order_by="position",
        )
        items: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                logger.warning("unexpected qdrant scroll item type=%s value=%r", type(item).__name__, item)
                continue
            payload = item.get("payload") or {}
            items.append(
                {
                    "id": item.get("id"),
                    "score": item.get("score"),
                    "file_path": payload.get("file_path"),
                    "file_name": payload.get("file_name"),
                    "chunk_id": payload.get("chunk_id"),
                    "heading_path": payload.get("heading_path"),
                    "position": payload.get("position"),
                    "branch": payload.get("branch"),
                    "commit_sha": payload.get("commit_sha"),
                    "content_hash": payload.get("content_hash"),
                    "text": payload.get("text"),
                    "text_preview": payload.get("text_preview"),
                    "payload": payload,
                }
            )
        return {
            "file_path": file_path,
            "count": len(items),
            "items": items,
        }

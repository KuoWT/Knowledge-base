from __future__ import annotations

import logging
import queue
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .qdrant import HttpQdrantWriter, LocalQdrantWriter, NoopQdrantWriter
from .store import Store, utcnow_iso
from .sync import read_repo_markdown_files, run_git, sync_repository


logger = logging.getLogger("knowledge_base_api.service")


@dataclass
class EnqueuedSync:
    task_id: str
    status: str


class HermesService:
    def __init__(self, config, store: Store) -> None:
        self.config = config
        self.store = store
        self.queue: queue.Queue[str] = queue.Queue()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def qdrant_writer(self):
        if self.config.qdrant_url:
            return HttpQdrantWriter(self.config.qdrant_url)
        return LocalQdrantWriter()

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

    def schedule_check(self) -> None:
        logger.info("scheduler check started")
        last = self.store.get_value("last_synced_sha")
        head = self._git_head()
        if head and head != last:
            logger.info("scheduler detected new head head=%s last_synced_sha=%s", head, last)
            self.enqueue_sync(
                source="scheduler",
                event_type="scheduled_check",
                project_id=None,
                branch=self.config.main_branch,
                commit_sha=head,
                delivery_id=None,
                trigger_reason="scheduler_catchup",
            )
            return
        failed = self.store.list_tasks("status = ?", ("failed",))
        if failed:
            logger.info("scheduler found failed tasks count=%s", len(failed))
            self.enqueue_sync(
                source="scheduler",
                event_type="retry_failed",
                project_id=None,
                branch=self.config.main_branch,
                commit_sha=head,
                delivery_id=None,
                trigger_reason="scheduler_retry",
            )

    def _git_head(self) -> str | None:
        result = run_git(self.config.repo_path, "rev-parse", "HEAD")
        if result.returncode != 0:
            return None
        return result.stdout.strip()

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
        result = run_git(self.config.repo_path, "pull", "--ff-only")
        if result.returncode != 0:
            logger.error("git pull failed task_id=%s stderr=%s", task_id, result.stderr.strip())
            raise RuntimeError(result.stderr.strip() or "git pull failed")
        logger.info("git pull ok task_id=%s branch=%s", task_id, branch)
        writer = self.qdrant_writer()
        result = sync_repository(
            repo_path=self.config.repo_path,
            store=self.store,
            qdrant_writer=writer,
            task_id=task_id,
            commit_sha=commit_sha,
            branch=branch,
            collection=self.config.qdrant_collection,
        )
        logger.info(
            "sync completed task_id=%s changed_files=%s upserted=%s deleted=%s",
            task_id,
            len(result.get("changed_files", [])),
            result.get("upserted"),
            result.get("deleted"),
        )
        for point in result.get("points", []):
            self.store.add_index_record(
                task_id=task_id,
                file_path=point.payload["file_path"],
                chunk_id=point.id,
                payload={"collection": self.config.qdrant_collection, **point.to_json()},
            )

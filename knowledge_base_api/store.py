from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SyncTask:
    task_id: str
    status: str
    source: str
    event_type: str | None
    project_id: str | None
    branch: str | None
    commit_sha: str | None
    delivery_id: str | None
    trigger_reason: str | None
    error: str | None
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                source TEXT NOT NULL,
                event_type TEXT,
                project_id TEXT,
                branch TEXT,
                commit_sha TEXT,
                delivery_id TEXT,
                trigger_reason TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS key_values (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS index_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def create_task(self, **kwargs: Any) -> SyncTask:
        task = SyncTask(
            task_id=kwargs["task_id"],
            status=kwargs["status"],
            source=kwargs["source"],
            event_type=kwargs.get("event_type"),
            project_id=kwargs.get("project_id"),
            branch=kwargs.get("branch"),
            commit_sha=kwargs.get("commit_sha"),
            delivery_id=kwargs.get("delivery_id"),
            trigger_reason=kwargs.get("trigger_reason"),
            error=kwargs.get("error"),
            created_at=kwargs.get("created_at") or utcnow_iso(),
            updated_at=kwargs.get("updated_at") or utcnow_iso(),
            started_at=kwargs.get("started_at"),
            finished_at=kwargs.get("finished_at"),
        )
        self.conn.execute(
            """
            INSERT INTO sync_tasks (
                task_id, status, source, event_type, project_id, branch,
                commit_sha, delivery_id, trigger_reason, error,
                created_at, updated_at, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.status,
                task.source,
                task.event_type,
                task.project_id,
                task.branch,
                task.commit_sha,
                task.delivery_id,
                task.trigger_reason,
                task.error,
                task.created_at,
                task.updated_at,
                task.started_at,
                task.finished_at,
            ),
        )
        self.conn.commit()
        return task

    def update_task(self, task_id: str, **kwargs: Any) -> SyncTask:
        row = self.get_task(task_id)
        if row is None:
            raise KeyError(task_id)
        updates = {**row.__dict__, **kwargs}
        updates["updated_at"] = utcnow_iso()
        self.conn.execute(
            """
            UPDATE sync_tasks
               SET status = ?, source = ?, event_type = ?, project_id = ?,
                   branch = ?, commit_sha = ?, delivery_id = ?,
                   trigger_reason = ?, error = ?, created_at = ?,
                   updated_at = ?, started_at = ?, finished_at = ?
             WHERE task_id = ?
            """,
            (
                updates["status"],
                updates["source"],
                updates["event_type"],
                updates["project_id"],
                updates["branch"],
                updates["commit_sha"],
                updates["delivery_id"],
                updates["trigger_reason"],
                updates["error"],
                updates["created_at"],
                updates["updated_at"],
                updates["started_at"],
                updates["finished_at"],
                task_id,
            ),
        )
        self.conn.commit()
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> SyncTask | None:
        row = self.conn.execute("SELECT * FROM sync_tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return SyncTask(**dict(row))

    def list_tasks(self, where: str = "", params: tuple[Any, ...] = ()) -> list[SyncTask]:
        query = "SELECT * FROM sync_tasks"
        if where:
            query += " WHERE " + where
        query += " ORDER BY created_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [SyncTask(**dict(row)) for row in rows]

    def set_value(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO key_values(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, utcnow_iso()),
        )
        self.conn.commit()

    def get_value(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM key_values WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["value"]

    def add_index_record(self, task_id: str, file_path: str, chunk_id: str, payload: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO index_records(task_id, file_path, chunk_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, file_path, chunk_id, json.dumps(payload, ensure_ascii=False), utcnow_iso()),
        )
        self.conn.commit()

    def list_index_records(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT file_path, chunk_id, payload_json, created_at FROM index_records WHERE task_id = ?",
            (task_id,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["file_path"] = row["file_path"]
            payload["chunk_id"] = row["chunk_id"]
            payload["created_at"] = row["created_at"]
            result.append(payload)
        return result

    def list_index_record_ids_for_file(self, file_path: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT chunk_id FROM index_records WHERE file_path = ? ORDER BY created_at ASC",
            (file_path,),
        ).fetchall()
        return [row["chunk_id"] for row in rows]

    def list_index_record_file_paths(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT file_path FROM index_records ORDER BY file_path ASC"
        ).fetchall()
        return [row["file_path"] for row in rows]

    def delete_index_records_for_file(self, file_path: str) -> None:
        self.conn.execute("DELETE FROM index_records WHERE file_path = ?", (file_path,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

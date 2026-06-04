from __future__ import annotations

import json
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import utcnow_iso
import logging


logger = logging.getLogger("hermes.server")


class HermesServer:
    def __init__(self, config, store, service) -> None:
        self.config = config
        self.store = store
        self.service = service
        self.httpd = None
        self._lock = threading.Lock()

    def make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _send_json(self, status: int, payload: dict) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else b""
                if not body:
                    return {}
                return json.loads(body.decode("utf-8"))

            def log_message(self, fmt, *args):  # noqa: N802
                return

            def do_POST(self):  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/webhooks/gitlab":
                    self.handle_gitlab_webhook()
                    return
                if parsed.path == "/api/v1/sync-tasks":
                    self.handle_create_task()
                    return
                if parsed.path.endswith("/retry"):
                    self.handle_retry_task(parsed.path)
                    return
                if parsed.path == "/api/v1/reindex":
                    self.handle_reindex()
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self.handle_health()
                    return
                if parsed.path == "/api/v1/sync-tasks":
                    self.handle_list_tasks(parsed.query)
                    return
                if parsed.path.startswith("/api/v1/sync-tasks/"):
                    self.handle_get_task(parsed.path)
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            def handle_gitlab_webhook(self):
                logger.info("webhook received path=%s remote=%s", self.path, self.client_address[0])
                if server.config.webhook_token:
                    token = self.headers.get("X-Gitlab-Token")
                    if token != server.config.webhook_token:
                        logger.warning("webhook rejected invalid token remote=%s", self.client_address[0])
                        self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid_token"})
                        return
                payload = self._read_json()
                event_type = payload.get("event_type") or payload.get("object_kind")
                if event_type not in {"merge", "merge_request", "merge_request_merged", "push"}:
                    logger.warning("webhook rejected unsupported event_type=%s", event_type)
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "unsupported_event"})
                    return
                if event_type == "push":
                    ref = payload.get("ref", "")
                    if not ref.endswith(f"/{server.config.main_branch}"):
                        logger.info("webhook ignored non-main push ref=%s", ref)
                        self._send_json(HTTPStatus.OK, {"status": "ignored"})
                        return
                task = server.service.enqueue_sync(
                    source="gitlab_webhook",
                    event_type=event_type,
                    project_id=str(payload.get("project_id") or payload.get("project", {}).get("id") or ""),
                    branch=payload.get("branch") or payload.get("ref_name") or server.config.main_branch,
                    commit_sha=payload.get("after_sha") or payload.get("checkout_sha") or payload.get("commit_sha"),
                    delivery_id=self.headers.get("X-Gitlab-Delivery") or payload.get("delivery_id"),
                    trigger_reason="webhook",
                )
                logger.info("webhook accepted task_id=%s event_type=%s branch=%s", task.task_id, event_type, task.branch)
                self._send_json(HTTPStatus.ACCEPTED, {"task_id": task.task_id, "status": task.status})

            def handle_create_task(self):
                payload = self._read_json()
                task = server.service.enqueue_sync(
                    source=payload.get("source", "api"),
                    event_type=payload.get("event_type"),
                    project_id=str(payload.get("project_id") or ""),
                    branch=payload.get("branch") or server.config.main_branch,
                    commit_sha=payload.get("commit_sha"),
                    delivery_id=payload.get("delivery_id"),
                    trigger_reason=payload.get("trigger_reason") or "api",
                )
                logger.info("api task created task_id=%s source=%s", task.task_id, task.source)
                self._send_json(HTTPStatus.ACCEPTED, {"task_id": task.task_id, "status": task.status})

            def handle_get_task(self, path: str):
                task_id = path.rsplit("/", 1)[-1]
                task = server.store.get_task(task_id)
                if task is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "task_not_found"})
                    return
                self._send_json(HTTPStatus.OK, task.__dict__)

            def handle_list_tasks(self, query: str):
                params = parse_qs(query)
                status = params.get("status", [None])[0]
                source = params.get("source", [None])[0]
                where = []
                values = []
                if status:
                    where.append("status = ?")
                    values.append(status)
                if source:
                    where.append("source = ?")
                    values.append(source)
                tasks = server.store.list_tasks(" AND ".join(where), tuple(values))
                self._send_json(HTTPStatus.OK, {"items": [task.__dict__ for task in tasks]})

            def handle_retry_task(self, path: str):
                task_id = path.split("/")[-2]
                task = server.service.retry_task(task_id)
                logger.info("task retry requested task_id=%s", task.task_id)
                self._send_json(HTTPStatus.ACCEPTED, {"task_id": task.task_id, "status": task.status})

            def handle_reindex(self):
                payload = self._read_json()
                task = server.service.enqueue_sync(
                    source="manual_reindex",
                    event_type="reindex",
                    project_id=str(payload.get("project_id") or ""),
                    branch=payload.get("branch") or server.config.main_branch,
                    commit_sha=payload.get("commit_sha"),
                    delivery_id=payload.get("delivery_id"),
                    trigger_reason=payload.get("reason") or "manual_rebuild",
                    paths=payload.get("paths") or [],
                    full_repository=payload.get("scope") == "repository",
                )
                logger.info("manual reindex requested task_id=%s scope=%s", task.task_id, payload.get("scope"))
                self._send_json(HTTPStatus.ACCEPTED, {"task_id": task.task_id, "status": task.status})

            def handle_health(self):
                logger.debug("health check remote=%s", self.client_address[0])
                payload = {
                    "status": "ok",
                    "service": "hermes",
                    "timestamp": utcnow_iso(),
                }
                self._send_json(HTTPStatus.OK, payload)

        return Handler

    def serve_forever(self) -> None:
        self.httpd = ThreadingHTTPServer((self.config.host, self.config.port), self.make_handler())
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()

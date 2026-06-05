from __future__ import annotations

import json
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import utcnow_iso
import logging


logger = logging.getLogger("kb_api.server")


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
            UI_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Knowledge Base API Task Monitor</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b1020;
      --panel: #121a33;
      --panel-2: #18213f;
      --text: #e7ecff;
      --muted: #9aa7d6;
      --line: #26335f;
      --accent: #7c9cff;
      --good: #52d273;
      --warn: #f5c451;
      --bad: #ff6b6b;
      --chip: #223058;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(124,156,255,.18), transparent 30%),
        radial-gradient(circle at top right, rgba(82,210,115,.12), transparent 22%),
        var(--bg);
      color: var(--text);
    }
    .wrap { max-width: 1320px; margin: 0 auto; padding: 32px 20px 40px; }
    header {
      display: flex; justify-content: space-between; gap: 20px; align-items: end; flex-wrap: wrap;
      margin-bottom: 22px;
    }
    h1 { margin: 0; font-size: 30px; letter-spacing: .02em; }
    .sub { margin-top: 8px; color: var(--muted); }
    .toolbar {
      display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
      padding: 14px; background: rgba(18,26,51,.9); border: 1px solid var(--line); border-radius: 16px;
      margin-bottom: 18px;
    }
    select, button {
      border: 1px solid var(--line); border-radius: 10px; background: var(--panel-2); color: var(--text);
      padding: 10px 12px; font-size: 14px;
    }
    button { cursor: pointer; }
    button:hover { border-color: var(--accent); }
    .grid {
      display: grid; grid-template-columns: 1.45fr .9fr; gap: 18px;
    }
    .card {
      background: rgba(18,26,51,.92); border: 1px solid var(--line); border-radius: 18px;
      overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,.22);
    }
    .card h2 {
      margin: 0; padding: 16px 18px; font-size: 16px; border-bottom: 1px solid var(--line);
      background: rgba(24,33,63,.82);
    }
    .card-body { padding: 16px 18px 18px; }
    .stats {
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px;
    }
    .stat {
      background: var(--panel-2); border: 1px solid var(--line); border-radius: 14px; padding: 12px;
    }
    .stat .label { color: var(--muted); font-size: 12px; }
    .stat .value { margin-top: 8px; font-size: 22px; font-weight: 700; }
    table { width: 100%; border-collapse: collapse; }
    thead th {
      text-align: left; font-size: 12px; letter-spacing: .04em; text-transform: uppercase; color: var(--muted);
      padding: 12px 10px; border-bottom: 1px solid var(--line);
    }
    tbody td {
      padding: 12px 10px; border-bottom: 1px solid rgba(38,51,95,.6); vertical-align: top;
      font-size: 14px;
    }
    tbody tr:hover { background: rgba(124,156,255,.07); cursor: pointer; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
    .chip {
      display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 999px;
      background: var(--chip); border: 1px solid var(--line); font-size: 12px;
    }
    .status-queued { color: var(--warn); }
    .status-running { color: var(--accent); }
    .status-succeeded { color: var(--good); }
    .status-failed { color: var(--bad); }
    .details {
      white-space: pre-wrap; word-break: break-word;
      background: #091022; border: 1px solid var(--line); border-radius: 14px;
      padding: 14px; min-height: 280px; color: var(--text); font-size: 13px; line-height: 1.5;
    }
    .muted { color: var(--muted); }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; background: rgba(124,156,255,.12); color: var(--text); font-size: 12px; }
    .footer { margin-top: 16px; color: var(--muted); font-size: 12px; }
    @media (max-width: 980px) {
      .grid { grid-template-columns: 1fr; }
      .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 640px) {
      .stats { grid-template-columns: 1fr; }
      h1 { font-size: 24px; }
      .wrap { padding: 18px 12px 28px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>Knowledge Base API Task Monitor</h1>
        <div class="sub">即時查看 webhook / API 建立的同步任務，點選任務可檢視詳細內容與重試。</div>
      </div>
      <div class="actions">
        <button id="refreshBtn">Refresh</button>
        <button id="retrySelectedBtn">Retry Selected</button>
      </div>
    </header>

    <div class="toolbar">
      <label class="chip">Status
        <select id="statusFilter">
          <option value="">All</option>
          <option value="queued">queued</option>
          <option value="running">running</option>
          <option value="succeeded">succeeded</option>
          <option value="failed">failed</option>
          <option value="retrying">retrying</option>
        </select>
      </label>
      <label class="chip">Source
        <select id="sourceFilter">
          <option value="">All</option>
          <option value="gitlab_webhook">gitlab_webhook</option>
          <option value="api">api</option>
          <option value="manual_reindex">manual_reindex</option>
        </select>
      </label>
      <span class="muted">Auto refresh: 5s</span>
      <span class="pill" id="summaryText">loading...</span>
    </div>

    <div class="grid">
      <section class="card">
        <h2>Tasks</h2>
        <div class="card-body" style="padding:0;">
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Source</th>
                <th>Branch</th>
                <th>Commit</th>
                <th>Updated</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="taskTable"></tbody>
          </table>
        </div>
      </section>

      <section class="card">
        <h2>Task Detail</h2>
        <div class="card-body">
          <div class="details" id="detailPane">Select a task to inspect its full payload and status history.</div>
        </div>
      </section>
    </div>

    <div class="footer">Endpoints: /health, /ready, /api/v1/sync-tasks, /api/v1/sync-tasks/{task_id}, /api/v1/sync-tasks/{task_id}/retry</div>
  </div>

  <script>
    const state = { tasks: [], selectedTaskId: null, timer: null };

    const els = {
      taskTable: document.getElementById('taskTable'),
      detailPane: document.getElementById('detailPane'),
      statusFilter: document.getElementById('statusFilter'),
      sourceFilter: document.getElementById('sourceFilter'),
      summaryText: document.getElementById('summaryText'),
      refreshBtn: document.getElementById('refreshBtn'),
      retrySelectedBtn: document.getElementById('retrySelectedBtn'),
    };

    function escapeText(value) {
      return String(value ?? '');
    }

    function formatTs(value) {
      return value ? new Date(value).toLocaleString() : '-';
    }

    function statusClass(value) {
      return `status-${value || 'queued'}`;
    }

    function renderSummary(items) {
      const counts = items.reduce((acc, item) => {
        acc[item.status || 'unknown'] = (acc[item.status || 'unknown'] || 0) + 1;
        return acc;
      }, {});
      const total = items.length;
      els.summaryText.textContent = `total ${total} | queued ${counts.queued || 0} | running ${counts.running || 0} | succeeded ${counts.succeeded || 0} | failed ${counts.failed || 0}`;
    }

    function renderRows(items) {
      if (!items.length) {
        els.taskTable.innerHTML = '<tr><td colspan="7" class="muted" style="padding:16px 10px;">No tasks found.</td></tr>';
        return;
      }
      els.taskTable.innerHTML = items.map((task) => `
        <tr data-task-id="${escapeText(task.task_id)}">
          <td class="mono">${escapeText(task.task_id)}</td>
          <td><span class="chip ${statusClass(task.status)}">${escapeText(task.status)}</span></td>
          <td>${escapeText(task.source)}</td>
          <td>${escapeText(task.branch || '-')}</td>
          <td class="mono">${escapeText(task.commit_sha || '-')}</td>
          <td>${formatTs(task.updated_at)}</td>
          <td><button data-retry="${escapeText(task.task_id)}">Retry</button></td>
        </tr>
      `).join('');

      for (const row of els.taskTable.querySelectorAll('tr[data-task-id]')) {
        row.addEventListener('click', () => selectTask(row.dataset.taskId));
      }
      for (const button of els.taskTable.querySelectorAll('button[data-retry]')) {
        button.addEventListener('click', async (event) => {
          event.stopPropagation();
          await retryTask(button.dataset.retry);
        });
      }
    }

    function renderDetail(task) {
      if (!task) {
        els.detailPane.textContent = 'Select a task to inspect its full payload and status history.';
        return;
      }
      els.detailPane.textContent = JSON.stringify(task, null, 2);
    }

    async function fetchTasks() {
      const params = new URLSearchParams();
      if (els.statusFilter.value) params.set('status', els.statusFilter.value);
      if (els.sourceFilter.value) params.set('source', els.sourceFilter.value);
      const url = '/api/v1/sync-tasks' + (params.toString() ? `?${params}` : '');
      const response = await fetch(url);
      if (!response.ok) throw new Error(`failed to load tasks: ${response.status}`);
      const data = await response.json();
      state.tasks = data.items || [];
      renderSummary(state.tasks);
      renderRows(state.tasks);
      if (state.selectedTaskId && !state.tasks.some((task) => task.task_id === state.selectedTaskId)) {
        state.selectedTaskId = null;
      }
      if (state.selectedTaskId) {
        const selected = state.tasks.find((task) => task.task_id === state.selectedTaskId);
        renderDetail(selected || null);
      }
    }

    async function selectTask(taskId) {
      state.selectedTaskId = taskId;
      const response = await fetch(`/api/v1/sync-tasks/${encodeURIComponent(taskId)}`);
      if (!response.ok) {
        renderDetail({ error: `Failed to load task ${taskId}`, status: response.status });
        return;
      }
      const task = await response.json();
      renderDetail(task);
      for (const row of els.taskTable.querySelectorAll('tr[data-task-id]')) {
        row.style.background = row.dataset.taskId === taskId ? 'rgba(124,156,255,.12)' : '';
      }
    }

    async function retryTask(taskId) {
      const response = await fetch(`/api/v1/sync-tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST' });
      if (!response.ok) {
        alert(`Retry failed: ${response.status}`);
        return;
      }
      await refresh();
      await selectTask(taskId);
    }

    async function refresh() {
      try {
        await fetchTasks();
      } catch (error) {
        els.summaryText.textContent = 'failed to load tasks';
        els.taskTable.innerHTML = '<tr><td colspan="7" class="muted" style="padding:16px 10px;">Failed to load tasks. Check API logs.</td></tr>';
        els.detailPane.textContent = String(error);
      }
    }

    els.refreshBtn.addEventListener('click', refresh);
    els.retrySelectedBtn.addEventListener('click', async () => {
      if (!state.selectedTaskId) {
        alert('Select a task first.');
        return;
      }
      await retryTask(state.selectedTaskId);
    });
    els.statusFilter.addEventListener('change', refresh);
    els.sourceFilter.addEventListener('change', refresh);

    refresh();
    state.timer = setInterval(refresh, 5000);
  </script>
</body>
</html>
"""

            def _send_json(self, status: int, payload: dict) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _send_html(self, status: int, html: str) -> None:
                data = html.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
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
                if parsed.path == "/api/v1/search":
                    self.handle_search(parsed.query)
                    return
                if parsed.path == "/api/v1/documents":
                    self.handle_document(parsed.query)
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path in {"/", "/ui"}:
                    self.handle_ui()
                    return
                if parsed.path == "/health":
                    self.handle_health()
                    return
                if parsed.path == "/ready":
                    self.handle_ready()
                    return
                if parsed.path == "/api/v1/sync-tasks":
                    self.handle_list_tasks(parsed.query)
                    return
                if parsed.path.startswith("/api/v1/sync-tasks/"):
                    self.handle_get_task(parsed.path)
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            def handle_ui(self):
                logger.debug("ui requested remote=%s path=%s", self.client_address[0], self.path)
                self._send_html(HTTPStatus.OK, self.UI_HTML)

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
                if event_type != "merge_request":
                    logger.warning("webhook rejected unsupported event_type=%s", event_type)
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "unsupported_event"})
                    return
                object_attributes = payload.get("object_attributes") or {}
                action = object_attributes.get("action")
                target_branch = object_attributes.get("target_branch") or payload.get("target_branch")
                if action != "merge":
                    logger.info("webhook ignored non-merge action=%s", action)
                    self._send_json(HTTPStatus.OK, {"status": "ignored"})
                    return
                if target_branch != server.config.main_branch:
                    logger.info(
                        "webhook ignored non-target branch target_branch=%s expected=%s",
                        target_branch,
                        server.config.main_branch,
                    )
                    self._send_json(HTTPStatus.OK, {"status": "ignored"})
                    return
                task = server.service.enqueue_sync(
                    source="gitlab_webhook",
                    event_type=event_type,
                    project_id=str(payload.get("project_id") or payload.get("project", {}).get("id") or ""),
                    branch=target_branch,
                    commit_sha=(
                        object_attributes.get("merge_commit_sha")
                        or object_attributes.get("squash_commit_sha")
                        or object_attributes.get("last_commit", {}).get("id")
                        or payload.get("after_sha")
                        or payload.get("checkout_sha")
                        or payload.get("commit_sha")
                    ),
                    delivery_id=self.headers.get("X-Gitlab-Delivery") or payload.get("delivery_id"),
                    trigger_reason="webhook",
                )
                logger.info(
                    "webhook accepted task_id=%s event_type=%s action=%s target_branch=%s",
                    task.task_id,
                    event_type,
                    action,
                    target_branch,
                )
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

            def handle_search(self, query: str):
                params = parse_qs(query)
                query_text = params.get("q", [""])[0].strip()
                if not query_text:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "query_required"})
                    return
                limit_raw = params.get("limit", ["10"])[0]
                branch = params.get("branch", [None])[0]
                file_path = params.get("file_path", [None])[0] or params.get("path", [None])[0]
                try:
                    limit = int(limit_raw)
                except ValueError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_limit"})
                    return
                try:
                    result = server.service.search_documents(
                        query_text,
                        limit=limit,
                        file_path=file_path,
                        branch=branch,
                    )
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                logger.info(
                    "search requested query=%s limit=%s file_path=%s branch=%s remote=%s",
                    query_text,
                    limit,
                    file_path,
                    branch,
                    self.client_address[0],
                )
                self._send_json(HTTPStatus.OK, result)

            def handle_document(self, query: str):
                params = parse_qs(query)
                file_path = params.get("path", [""])[0].strip() or params.get("file_path", [""])[0].strip()
                if not file_path:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "path_required"})
                    return
                branch = params.get("branch", [None])[0]
                limit_raw = params.get("limit", ["100"])[0]
                try:
                    limit = int(limit_raw)
                except ValueError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_limit"})
                    return
                try:
                    result = server.service.get_document_chunks(
                        file_path,
                        branch=branch,
                        limit=limit,
                    )
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                logger.info(
                    "document requested file_path=%s branch=%s remote=%s",
                    file_path,
                    branch,
                    self.client_address[0],
                )
                self._send_json(HTTPStatus.OK, result)

            def handle_health(self):
                logger.debug("health check remote=%s", self.client_address[0])
                payload = {
                    "status": "ok",
                    "service": "kb_api",
                    "timestamp": utcnow_iso(),
                }
                self._send_json(HTTPStatus.OK, payload)

            def handle_ready(self):
                checks = {
                    "db": self._check_db(),
                    "repo": self._check_repo(),
                    "git": self._check_git(),
                    "qdrant": self._check_qdrant(),
                }
                ready = all(checks.values())
                payload = {
                    "status": "ok" if ready else "not_ready",
                    "service": "kb_api",
                    "checks": checks,
                    "timestamp": utcnow_iso(),
                }
                self._send_json(HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE, payload)

            def _check_db(self) -> bool:
                try:
                    server.store.conn.execute("SELECT 1")
                    return True
                except Exception:
                    logger.exception("ready check db failed")
                    return False

            def _check_repo(self) -> bool:
                try:
                    from pathlib import Path

                    path = Path(server.config.repo_path)
                    return path.exists() and path.is_dir()
                except Exception:
                    logger.exception("ready check repo failed")
                    return False

            def _check_git(self) -> bool:
                try:
                    from .sync import run_git

                    result = run_git(server.config.repo_path, "rev-parse", "--git-dir")
                    return result.returncode == 0
                except Exception:
                    logger.exception("ready check git failed")
                    return False

            def _check_qdrant(self) -> bool:
                try:
                    server.service.ensure_qdrant_collection()
                    return True
                except Exception:
                    logger.exception("ready check qdrant failed")
                    return False

        return Handler

    def serve_forever(self) -> None:
        self.httpd = ThreadingHTTPServer((self.config.host, self.config.port), self.make_handler())
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()

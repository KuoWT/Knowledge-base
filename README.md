# Knowledge Base API

This repo contains a minimal, dependency-free Python implementation of the knowledge base sync flow:

- GitLab webhook ingestion
- API sync task queue
- Markdown parsing and chunking
- Embedding write abstraction
- Qdrant write abstraction

## Current Flow

```mermaid
flowchart TD
  A[Engineer / User] --> B[Obsidian]
  B --> C[Git Push]
  C --> D[GitLab]
  D --> E[Webhook / API]

  E --> F[POST /webhooks/gitlab]
  E --> G[POST /api/v1/sync-tasks]
  E --> H[POST /api/v1/reindex]

  F --> I[Validate token / parse event]
  G --> J[Create sync task]
  H --> J
  I --> J

  J --> K[SQLite sync_tasks]
  K --> L[Background worker queue]
  L --> M[git pull --ff-only]
  M --> N[Detect changed files]
  N --> O[Process .md only]
  O --> P[Markdown parse / chunk]
  P --> Q[Embedding]
  Q --> R[Qdrant writer]
  R --> S[Qdrant]

  J --> T[Task status]
  T --> U[GET /api/v1/sync-tasks]
  T --> V[GET /api/v1/sync-tasks/{task_id}]
  T --> W[POST /api/v1/sync-tasks/{task_id}/retry]

  X[GET /health] --> Y[Liveness]
  Z[GET /ready] --> AA[DB / Repo / Git checks]
```

## Run

```bash
python3 -m knowledge_base_api.main
```

## Docker

```bash
docker build -t knowledge-base-api:latest .
docker run --rm -p 8080:8080 \
  -e KB_API_HOST=0.0.0.0 \
  -e KB_API_REPO_PATH=/repo \
  -v "$PWD":/repo \
  knowledge-base-api:latest
```

## Docker Compose Settings

Use `.env` for local deployment:

```env
KB_API_HOST=0.0.0.0
KB_API_PORT=8080
KB_API_HOST_PORT=8081
KB_API_DB_PATH=/data/knowledge-base-api.db
KB_API_REPO_PATH=/repo
KB_API_MAIN_BRANCH=main
KB_API_WEBHOOK_TOKEN=your-webhook-token
KB_API_LOG_LEVEL=INFO
QDRANT_URL=
QDRANT_COLLECTION=knowledge_base
```

Compose mapping:

- `KB_API_HOST_PORT` is the host port exposed on your machine.
- `KB_API_DB_PATH` is the SQLite file inside the container.
- `KB_API_REPO_PATH=/repo` means the container expects a mounted Git repository at `/repo`.
- `./:/repo` in `docker-compose.yml` mounts the current project directory into the container.
- If you want to use a different local repository, change the host-side volume path in `docker-compose.yml` to that clone path.

Recommended host-side repo setup:

```bash
git clone <your GitLab repo URL> /opt/knowledge-base
```

Then adjust the compose volume if needed:

```yaml
volumes:
  - hermes_data:/data
  - /opt/knowledge-base:/repo
```

GitLab webhook settings:

- URL: `http://YOUR_SERVER_IP:8081/webhooks/gitlab`
- Secret token: same value as `KB_API_WEBHOOK_TOKEN`
- Recommended event: `Merge request events`
- The API checks `X-Gitlab-Token` against `KB_API_WEBHOOK_TOKEN`
- If you use an SSH remote, the container uses `StrictHostKeyChecking=accept-new` so the first connection can trust a new host key automatically; if your host blocks that flow, switch the remote to HTTPS or pre-seed `known_hosts` in your environment.

Health endpoints:

- `GET /health` returns service liveness
- `GET /ready` returns dependency readiness checks
- `GET /` or `GET /ui` opens the task monitor page

API endpoints:

- `POST /webhooks/gitlab`
- `POST /api/v1/sync-tasks`
- `GET /api/v1/sync-tasks`
- `GET /api/v1/sync-tasks/{task_id}`
- `POST /api/v1/sync-tasks/{task_id}/retry`
- `POST /api/v1/reindex`

Environment variables:

- `KB_API_HOST` default `127.0.0.1`
- `KB_API_PORT` default `8080`
- `KB_API_HOST_PORT` default `8080` for Docker Compose host mapping
- `KB_API_DB_PATH` default `./knowledge-base-api.db`
- `KB_API_REPO_PATH` default current working directory
- `KB_API_MAIN_BRANCH` default `main`
- `KB_API_WEBHOOK_TOKEN` optional shared token
- `KB_API_LOG_LEVEL` default `INFO`
- `QDRANT_URL` optional Qdrant REST endpoint
- `QDRANT_COLLECTION` default `knowledge_base`

## Notes

The implementation is intentionally small and standard-library only so it can be extended without dependency setup.

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

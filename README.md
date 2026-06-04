# Knowledge Base API

This repo contains a minimal, dependency-free Python implementation of the knowledge base sync flow:

- GitLab webhook ingestion
- API sync task queue
- Markdown parsing and chunking
- Embedding write abstraction
- Qdrant write abstraction

## Run

```bash
python3 -m knowledge_base_api.main
```

## Docker

```bash
docker build -t knowledge-base-api:latest .
docker run --rm -p 8080:8080 \
  -e HERMES_HOST=0.0.0.0 \
  -e HERMES_REPO_PATH=/repo \
  -v "$PWD":/repo \
  knowledge-base-api:latest
```

Environment variables:

- `HERMES_HOST` default `127.0.0.1`
- `HERMES_PORT` default `8080`
- `HERMES_DB_PATH` default `./knowledge-base-api.db`
- `HERMES_REPO_PATH` default current working directory
- `HERMES_MAIN_BRANCH` default `main`
- `HERMES_WEBHOOK_TOKEN` optional shared token
- `QDRANT_URL` optional Qdrant REST endpoint
- `QDRANT_COLLECTION` default `knowledge_base`

## Notes

The implementation is intentionally small and standard-library only so it can be extended without dependency setup.

# Monitoring Guide

This project emits structured JSON logs to stdout, which makes it easy to ship logs into Loki via Grafana Alloy or Promtail.

## Recommended path

Use Grafana Alloy as the preferred log collector.

- App logs go to stdout in JSON.
- Alloy scrapes Docker containers.
- Alloy parses the JSON log line.
- Loki receives low-cardinality labels plus structured fields.

## Why Alloy

- Docker log collection is built in.
- Alloy supports `loki.source.docker`, `loki.process`, and `loki.write`.
- Alloy is the preferred modern path for Loki log shipping.

## Labels

Use only stable, low-cardinality labels:

- `app=knowledge-base-api`
- `component=api`
- `env=prod`
- `team=knowledge-base`

Do not use high-cardinality labels for:

- `task_id`
- `commit_sha`
- `file_path`
- `branch`
- `path`

Keep those values in the JSON log body.

## Grafana Alloy

Reference config:

- [deploy/alloy-config.alloy](/Users/kevin/Documents/知識庫%202/deploy/alloy-config.alloy)

Minimal container run:

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/deploy/alloy-config.alloy:/etc/alloy/config.alloy \
  grafana/alloy:latest \
  run /etc/alloy/config.alloy
```

Useful LogQL queries:

```logql
{app="knowledge-base-api"}
{app="knowledge-base-api", level="ERROR"}
{app="knowledge-base-api", logger="kb_api.server"}
{app="knowledge-base-api"} |= "task failed"
{app="knowledge-base-api"} |= "request completed"
```

## Promtail

Promtail is still usable as a legacy option if you already operate it, but the Alloy path is preferred for new deployments.

Reference config:

- [deploy/promtail-config.yml](/Users/kevin/Documents/知識庫%202/deploy/promtail-config.yml)

Minimal container run:

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/deploy/promtail-config.yml:/etc/promtail/config.yml \
  grafana/promtail:latest \
  -config.file=/etc/promtail/config.yml
```

## Docker Compose labels

Suggested labels for the `knowledge-base-api` service:

```yaml
labels:
  app: knowledge-base-api
  component: api
  env: prod
  team: knowledge-base
```

## JSON log example

```json
{"timestamp":"2026-06-06T00:00:00+00:00","level":"INFO","logger":"kb_api.server","message":"request completed","remote":"127.0.0.1","method":"GET","path":"/health","status":200,"duration_ms":2.31}
```

## Notes

- Keep `KB_API_LOG_FORMAT=json` in Docker deployments.
- Use labels for service identity only.
- Use JSON fields for request-specific diagnostics.

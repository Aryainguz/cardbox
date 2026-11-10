# cardbox-server

An HTTP render service for cardbox, in Go. Submit a spec, follow the render live, download the video.

```
POST   /v1/renders               submit (YAML body, or JSON {"spec": ..., "webhook_url": ..., "reuse": true})
GET    /v1/renders               your renders, newest first (?limit=20&before=<RFC3339>)
GET    /v1/renders/{id}          one render
GET    /v1/renders/{id}/events   live progress, Server-Sent Events
GET    /v1/renders/{id}/video    the MP4 (Range requests supported)
DELETE /v1/renders/{id}          cancel
GET    /healthz  /metrics
```

## Design

```
            ┌────────────┐  202 + job   ┌──────────────┐  bounded chan  ┌──────────────┐
 client ───►│  API (mux) │─────────────►│ SQLite store │◄───────────────│ worker pool  │──► cardbox render
            │ auth, rate │◄── SSE ──────│  (WAL)       │   status/prog  │ N goroutines │    (subprocess,
            └────────────┘    hub       └──────────────┘                └──────┬───────┘     own pgroup)
                                ▲                                            │ @progress lines
                                └──────────── progress hub (fan-out) ◄───────┘
                                                                             └──► signed webhook (retries)
```

- **Backpressure:** the queue is a bounded channel. When it's full the API answers `503` with `Retry-After`
  instead of piling up work it can't finish.
- **Cancellation:** each render runs under a context with a timeout. `DELETE` cancels it, and the renderer
  runs in its own process group so the browser and ffmpeg children die with it.
- **Graceful shutdown:** on SIGTERM the server stops accepting work, lets running renders finish within a
  grace period, then cancels what's left. Jobs still queued or running are re-queued at the next start.
- **Live progress:** the Python renderer prints `@progress {json}` lines. The runner parses them, persists
  the latest, and publishes to a hub that fans out to SSE subscribers. Slow subscribers drop stale events
  rather than blocking the worker.
- **Idempotency:** `Idempotency-Key` headers make retried POSTs return the original job. Specs are content
  hashed, so re-submitting an identical spec returns the finished render (`Cardbox-Reused: true`).
- **Webhooks:** `webhook_url` gets a `render.succeeded|failed|canceled` POST signed with
  `Cardbox-Signature: t=<unix>,v1=<HMAC-SHA256("<t>.<body>")>`, retried with exponential backoff.
- **Multi-tenant:** API keys map to owners; every query is scoped by owner. Per-key token-bucket rate limits.
- **Observability:** JSON logs with request IDs, and Prometheus metrics (`cardbox_jobs`, `cardbox_queue_depth`,
  `cardbox_renders_running`).

## Configuration

| Variable | Default | |
| --- | --- | --- |
| `CARDBOX_ADDR` | `:8080` | listen address |
| `CARDBOX_DATA` | `./data` | database and renders |
| `CARDBOX_BIN` | `cardbox` | the cardbox CLI |
| `CARDBOX_WORKERS` | `2` | renders at once (each uses a browser and ffmpeg) |
| `CARDBOX_BACKLOG` | `64` | queued jobs beyond the running ones |
| `CARDBOX_RENDER_TIMEOUT_MIN` | `20` | per-render limit |
| `CARDBOX_API_KEYS` | (open) | `key1:alice,key2:bob`; empty = no auth, for local use |
| `CARDBOX_RATE_PER_MIN` / `CARDBOX_RATE_BURST` | `30` / `10` | per-key limits on writes |
| `CARDBOX_WEBHOOK_SECRET` | | HMAC secret for webhook signatures |
| `CARDBOX_PUBLIC_URL` | | base URL used in webhook payloads |
| `CARDBOX_VOICE_PYTHON` | | interpreter with the voice stack, if separate |
| `CARDBOX_SHUTDOWN_GRACE_SEC` | `60` | how long renders may finish on shutdown |

## Run

```bash
go run ./cmd/cardbox-server
# or, from the repo root
docker compose up --build
```

## Test

```bash
go test -race ./...
```

The API tests run against a real SQLite database and real HTTP/SSE, with a fake renderer.

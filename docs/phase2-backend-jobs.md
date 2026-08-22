# Phase 2 — Backend + Jobs

Phase 2 implements the durable backend foundation documented in Phase 0. The FastAPI API owns request validation, development-only authorization scaffolding, project-scoped job commands and queries, error envelopes, health/readiness, OpenAPI, and SSE. PostgreSQL is the source of truth; the Alembic migration creates the required Phase 0 entities plus durable idempotency and outbox records. Redis transports work only after the job, progress event, and outbox row commit together.

The worker consumes only `run_planning`. It transitions `QUEUED → PLANNING → BROWSER_INITIALIZING`, persists a deterministic `DRAFT` placeholder plan, and then stops. This is an explicit Phase 3 boundary: no browser exists, no source URL is navigated, and the placeholder is not AI-generated.

## Development commands

| Purpose | Command |
|---|---|
| Install | `uv pip install --system -e '.[dev]'` |
| Apply migrations | `alembic -c services/api/alembic.ini upgrade head` |
| Inspect migration state | `alembic -c services/api/alembic.ini current` |
| Run API | `uvicorn wde_api.main:app --reload` |
| Run worker | `python -m wde_api.worker` |
| Test | `pytest` |
| Lint | `ruff check services/api/src` |
| Format check | `ruff format --check services/api/src` |

The development identity is controlled by `DEV_PRINCIPAL_EMAIL` and exists only to keep every project and job operation behind a documented ownership boundary. It is not production authentication.

## Implemented contracts

`POST /api/jobs`, `GET /api/jobs/{job_id}`, `POST /api/jobs/{job_id}/cancel`, `GET /api/jobs/{job_id}/results`, `GET /api/jobs/{job_id}/files`, and `GET /api/jobs/{job_id}/events` match the Phase 0 API surface. Results and files correctly return empty structures until later extraction and exporter phases. The SSE endpoint replays retained ordered events after `Last-Event-ID` and waits without busy looping while a non-terminal job remains active.

## Explicit non-goals

This phase does not implement Playwright, URL navigation, redirects, DNS enforcement, browser workers, LLM planning, discovery, extraction, validation rules, data export, production deployment, or a full authentication system. The local artifact adapter is a storage port implementation; it does not create downloadable exports.

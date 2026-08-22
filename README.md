# Web Data Extraction Engine

A modular web data extraction engine for discovering, extracting, validating, transforming, and exporting structured data from accessible websites.

## Purpose

The long-term product will accept a website URL, a natural-language extraction request, optional requirements, crawl controls, and requested output formats. It will turn that intent into a bounded asynchronous workflow for discovery, browser-assisted capture, deterministic extraction, validation, and export.

The platform is designed for publicly accessible content that the user is permitted to access. It is not a chatbot or a simple scraper, and it will not bypass CAPTCHA, authentication, authorization, paywalls, access controls, or other security mechanisms.

## Technology direction

The planned direction uses a Next.js and TypeScript web client, a Python/FastAPI API, asynchronous Playwright browser workers, PostgreSQL for durable state, Redis for background-job transport, and an S3-compatible storage abstraction with local filesystem support during development. Data-processing libraries such as Pandas, BeautifulSoup4, lxml, and OpenPyXL will be introduced when their corresponding capabilities are implemented.

## Project status

**Phase 0 — Architecture**, **Phase 1 — Frontend**, **Phase 2 — Backend + Jobs**, **Phase 3 — Playwright Engine**, **Phase 4 — AI Planner**, **Phase 5 — Discovery Engine**, **Phase 6 — Extraction Engine**, **Phase 7 — Validation Engine**, **Phase 8 — Excel / CSV / JSON Export Engine**, and **Phase 9 — Progress + Results Experience** are complete. Phase 9 makes Data Loom a typed real client of the existing job status, cancellation, results, files, and SSE interfaces without changing pipeline behavior.

See the [Phase 0 architecture documentation](docs/architecture.md) for the system overview. Related contracts and decisions are documented in:

- [System design](docs/system-design.md)
- [Data model](docs/data-model.md)
- [API contracts](docs/api-contracts.md)
- [Job lifecycle](docs/job-lifecycle.md)
- [Browser policy](docs/browser-policy.md)
- [Security boundaries](docs/security-boundaries.md)
- [Storage architecture](docs/storage-and-operations.md)
- [Agent boundaries](docs/agent-boundaries.md)
- [Roadmap and phase boundaries](docs/phase-boundaries.md)
- [ADR-001: Modular asynchronous architecture](docs/decisions/ADR-001-architecture.md)
- [Phase 3 Playwright engine](docs/phase3-playwright-engine.md)
- [ADR-002: Browser artifact metadata](docs/decisions/ADR-002-browser-artifacts.md)
- [Phase 4 AI planner](docs/phase4-ai-planner.md)
- [Phase 5 discovery engine](docs/phase5-discovery.md)
- [Phase 6 extraction engine](docs/phase6-extraction.md)
- [Phase 7 validation engine](docs/phase7-validation.md)
- [Phase 8 export engine](docs/phase8-export.md)
- [Phase 9 progress and results](docs/phase9-progress-results.md)

## Local backend development

Copy `.env.example` to `.env`, then start PostgreSQL and Redis with `docker compose up -d postgres redis` when Docker is available. Install Python dependencies with `uv pip install --system -e '.[dev]'`, then install Chromium with `python -m playwright install chromium`. Apply the reproducible schema with `DATABASE_URL=postgresql+asyncpg://wde:wde@localhost:5432/wde alembic -c services/api/alembic.ini upgrade head`. Run the API with `uvicorn wde_api.main:app --reload`, the worker with `python -m wde_api.worker`, and use `/docs`, `/openapi.json`, `/health`, and `/ready` to inspect the API.

Run `pytest`, `ruff check services/api/src`, `ruff format --check services/api/src`, and `alembic -c services/api/alembic.ini current` before contributing. The optional `apps/web/lib/api-client.ts` is the Phase 1-compatible client seam; it does not replace the current mock UI flow.

Development continues incrementally. **Phase 9 — Results UI and progress experience** is the recommended next phase. It must consume durable export metadata without changing export data policies.

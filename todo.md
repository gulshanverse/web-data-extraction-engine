# Phase 1 Frontend Redesign Checklist

- [x] Read and map the complete attached redesign specification.
- [x] Replace the existing frontend implementation with the required Next.js application structure.
- [x] Define the replacement visual system, typography, semantic color tokens, and intentional light/dark behavior.
- [x] Rebuild the source, intent, configuration, output, execution, empty, results, and runs/history workspace states.
- [x] Add functional theme switching, inline form validation, accessible controls, mock pipeline transitions, and output interactions.
- [x] Validate desktop, tablet, mobile, light mode, dark mode, keyboard access, and reduced-motion behavior.
- [x] Apply a five-point visual self-critique and visual-review improvements.
- [x] Run lint, tests, type, build, secret, diff, documentation-integrity, and phase-boundary checks.
- [x] Commit and push the completed redesign to `main`.

## Phase 2 Backend + Jobs Checklist

- [x] Read and reconcile all Phase 0 architecture contracts with the Phase 2 requirements.
- [x] Create the Python API, domain, persistence, migration, storage, queue, worker, and test structure.
- [x] Define the PostgreSQL schema and reproducible Alembic migrations for the required Phase 2 entities.
- [x] Implement typed API contracts, URL policy, project/source persistence, durable idempotency, and health/readiness endpoints.
- [x] Implement compare-and-set lifecycle transitions, ordered progress events, cancellation, retry, outbox scheduling, and the Redis worker command.
- [x] Implement job status, results, file metadata, and SSE event-stream contracts without later-phase extraction engines.
- [x] Run database-backed integration tests, migrations, API-contract checks, security scans, and code-quality validation.
- [ ] Commit and push Phase 2 to `main` without implementing Phase 3 or later.

## Phase 3 Playwright Engine Checklist

- [x] Read the complete Phase 3 specification and reconcile all Phase 0 and Phase 2 browser contracts.
- [x] Add Playwright runtime dependencies, browser-engine interfaces, typed configuration, and local browser installation workflow.
- [x] Implement isolated context/page lifecycle management, controlled navigation, cleanup, metadata, screenshots, and structured browser events.
- [x] Implement DNS-aware initial and redirect policy checks, request/resource controls, limits, timeouts, cancellation checks, and safe application errors.
- [x] Integrate browser initialization work with the durable Phase 2 orchestrator, worker, job transitions, events, and artifact storage.
- [x] Add deterministic policy, lifecycle, redirect, cancellation, timeout, storage, worker, and integration tests.
- [x] Run Playwright, API, worker, migration, security, lint, format, type/static, build, and phase-boundary validation.
- [ ] Commit and push Phase 3 to `main` without implementing Phase 4 or later.

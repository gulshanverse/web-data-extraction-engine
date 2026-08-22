# Implementation Checklist

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
- [x] Commit and push Phase 2 to `main` without implementing Phase 3 or later.

## Phase 3 Playwright Engine Checklist

- [x] Read the complete Phase 3 specification and reconcile all Phase 0 and Phase 2 browser contracts.
- [x] Add Playwright runtime dependencies, browser-engine interfaces, typed configuration, and local browser installation workflow.
- [x] Implement isolated context/page lifecycle management, controlled navigation, cleanup, metadata, screenshots, and structured browser events.
- [x] Implement DNS-aware initial and redirect policy checks, request/resource controls, limits, timeouts, cancellation checks, and safe application errors.
- [x] Integrate browser initialization work with the durable Phase 2 orchestrator, worker, job transitions, events, and artifact storage.
- [x] Add deterministic policy, lifecycle, redirect, cancellation, timeout, storage, worker, and integration tests.
- [x] Run Playwright, API, worker, migration, security, lint, format, type/static, build, and phase-boundary validation.
- [x] Commit and push Phase 3 to `main` without implementing Phase 4 or later.

## Phase 4 AI Planner Checklist

- [x] Add a configured production provider abstraction and a deterministic test-only model implementation.
- [x] Define a strict, declarative, versioned plan schema and deterministic canonical SHA-256 hash.
- [x] Reject unsafe prompt-injection text, source changes, selector/code-like output, unknown properties, and limit or option mutation.
- [x] Persist validated plan audit metadata through migration `0003_planner_metadata`.
- [x] Replace the durable planning placeholder with claim, generation, completion, failure, cancellation, retry, and outbox-handoff behavior.
- [x] Preserve the `QUEUED → PLANNING → BROWSER_INITIALIZING` lifecycle and stop before discovery.
- [x] Add provider, schema, security, worker, persistence, safe API metadata, cancellation, retry, and browser-regression coverage.
- [x] Document local provider configuration, resource controls, logging, known limitations, and Phase 5 boundary.
- [ ] Run final migration, regression, lint, type/static, production-build, secret, and phase-boundary gates; commit and push Phase 4 to `main`.

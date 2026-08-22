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
- [x] Run final migration, regression, lint, type/static, production-build, secret, and phase-boundary gates; commit and push Phase 4 to `main`.

## Phase 5 Discovery Engine Checklist

- [x] Audit the implemented Phase 0–4 contracts, source, migrations, documentation, and tests before making Phase 5 changes.
- [x] Define typed discovery results, deterministic URL normalization, scope policy, and controlled inventory states.
- [x] Add durable page-inventory persistence, migration, deduplication, source attribution, and safe discovery metadata.
- [x] Implement discovery only through the existing worker/outbox lifecycle, reusing Phase 3 browser policy and cancellation controls.
- [x] Support source, link, pagination, sitemap, and relevant-link discovery interfaces without record extraction or selector generation.
- [x] Add discovery policy, URL, lifecycle, worker, persistence, cancellation, retry, and regression tests.
- [x] Document discovery architecture, limits, security boundaries, local configuration, and the Phase 6 boundary.
- [x] Run final migration, regression, lint, type/static, production-build, secret, and phase-boundary gates; commit and push Phase 5 to `main`.

## Phase 6 Extraction Engine Checklist

- [x] Audit Phase 0–5 contracts, source, migrations, documentation, and test suites before implementing extraction.
- [x] Define typed extraction results, bounded evidence/provenance, safe normalization, and deterministic record identity.
- [x] Extend browser contracts only for bounded rendered DOM and structured-data signals required by extraction.
- [x] Add durable extraction persistence, migration, page extraction metadata, cancellation, retry, idempotency, and Phase 7 handoff behavior.
- [x] Implement plan-driven extraction for structured data, tables, lists, cards, and detail pages without mutating discovery scope or plan fields.
- [x] Add extraction unit, security, lifecycle, worker, persistence, browser, normalization, and full regression coverage.
- [x] Document extraction architecture, configuration, evidence rules, security controls, known limitations, and the Phase 7 boundary.
- [x] Run final migration, regression, lint, type/static, production-build, secret, and phase-boundary gates; commit and push Phase 6 to `main`.

## Phase 7 Validation Engine Checklist

- [x] Audit Phase 0–6 contracts, source, migrations, documentation, and test suites before implementing validation.
- [x] Define typed validation outcomes, deterministic quality classification, rule results, summaries, and immutable-input constraints.
- [x] Add durable validation-result persistence, migration, record/page validation metadata, idempotency, retry, cancellation, and Phase 8 handoff behavior.
- [x] Implement schema, type, presence, format, evidence, consistency, duplicate, and cross-field checks without mutating extraction values.
- [x] Add validation unit, lifecycle, worker, persistence, security, summary, and full regression coverage.
- [x] Document validation semantics, quality policy, configuration, security controls, known limitations, and the Phase 8 boundary.
- [x] Run final migration, regression, lint, type/static, production-build, secret, and phase-boundary gates; commit and push Phase 7 to `main`.

## Phase 8 Excel / CSV / JSON Export Engine Checklist

- [x] Audit Phase 0–7 contracts, source, migrations, storage, documentation, and test suites before implementing exports.
- [x] Define a canonical validated export dataset, persisted export request policy, deterministic field order, and format metadata.
- [x] Implement deterministic CSV, JSON, and XLSX exporters with Unicode, nested-value, null, and spreadsheet/CSV injection protections.
- [x] Add durable export persistence, storage metadata, idempotency, cancellation, retry, progress, events, and safe download references.
- [x] Add export format, security, storage, lifecycle, policy, and full regression coverage.
- [x] Document export architecture, invalid-record policy, metadata/provenance policy, limits, security, configuration, and Phase 9 boundary.
- [x] Run final migration, regression, lint, type/static, production-build, secret, and phase-boundary gates; commit and push Phase 8 to `main`.

## Phase 9 Progress + Results Experience Checklist

- [x] Audit Phase 0–8 backend/frontend contracts, routes, SSE, export seams, documentation, and tests before implementing the product experience.
- [x] Preserve the Data Loom light/dark design system and define real job, progress, results, exports, history, and recovery states.
- [x] Replace mock lifecycle behavior with authorized backend API and SSE integration, including reconnection and terminal-state refresh behavior.
- [x] Implement responsive, accessible progress, record inspection, validation, export, history, error, cancellation, and retry presentation without backend lifecycle changes.
- [x] Add frontend integration, SSE, responsive, accessibility, empty/error/loading, and regression tests.
- [x] Document Phase 9 data flow, live updates, UX boundaries, known limitations, and the Phase 10 boundary.
- [x] Run final backend/frontend quality gates, screenshots, secret/boundary scans, commit, and push Phase 9 to `main`.

## Phase 10 PDF / DOCX / Document Formats Checklist

- [x] Audit Phase 0–9 contracts, canonical export dataset, storage, frontend seams, documentation, and tests before document-export work.
- [x] Define a versioned document profile, document data model, renderer registry, safe metadata policy, and rendering limits.
- [x] Implement deterministic PDF and DOCX renderers, with Markdown, TXT, and HTML document forms where supported, from the canonical export dataset only.
- [x] Add document rendering, Unicode, long-text, layout, link, safety, storage, lifecycle, and regression tests.
- [x] Document document profiles, format-specific behavior, metadata, provenance, limits, safety, testing, and Phase 11 boundary.
- [x] Run final quality gates, commit, and push Phase 10 to `main`.

## Phase 10R Durable Export Lifecycle Repair Checklist

- [x] Verify the Phase 8/10 export-worker-storage-files lifecycle gap against actual code and the full corrective specification.
- [x] Reuse the canonical validated dataset and existing export models to define one durable export command, request identity, status, and safe file metadata contract.
- [x] Wire existing tabular and document writers into the existing outbox, worker, storage, generated-file persistence, authorization, and minimal Phase 9 results recognition paths.
- [x] Add lifecycle, idempotency, cancellation, retry, storage, document, file authorization, API, worker, and frontend regression coverage.
- [x] Reconcile export/document lifecycle documentation, configuration, test matrix, and Phase 11/12 boundaries.
- [x] Run migrations and complete backend/frontend/security/boundary gates, then commit and push Phase 10R to `main`.

## Phase 9R Real Results Projection Repair Checklist

- [x] Verify the reported mock-results and hard-coded validation projection defect against actual Phase 6–10R code and baseline tests.
- [x] Define the smallest compatible API projection for durable record values, validation outcomes, job-wide metrics, and pagination.
- [x] Replace backend placeholder validation data and frontend sample result presentation with authorized real durable data while preserving Data Loom design.
- [x] Add backend/frontend regressions for validation states, metrics, pagination, empty/error states, authorization, SSE completion refresh, and Phase 10R files.
- [x] Run complete Phase 9R quality gates, update documentation, commit, and push the repair to `main`.

## Phase 11 Security + Testing Checklist

- [x] Complete a repository-wide Phase 0–10R/9R security preflight and record baseline results.
- [x] Create the threat model, hardening record, test matrix, findings register, residual risks, and production-readiness assessment.
- [x] Implement bounded input, browser-policy, authorization, API, storage, queue, worker, logging, error, and resource hardening without Phase 12 work.
- [x] Add adversarial SSRF, URL, AI, cross-user, SSE, export, document, filesystem, resource, concurrency, cancellation, retry, and recovery coverage.
- [x] Run full backend/frontend/migration/dependency/secret/boundary validation, commit, and push Phase 11 to `main`.

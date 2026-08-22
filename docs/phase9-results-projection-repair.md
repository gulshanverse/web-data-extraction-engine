# Phase 9R — Real Results Projection Repair

## Corrected data path

The Phase 9 results workspace no longer presents production sample rows or fixed result metrics. For an authorized job, the API now projects only durable `Record` values and the most recent completed `ValidationRun` outcomes. The existing Phase 9 workspace loads that typed projection when the job reaches `COMPLETED`, keeps the existing SSE status-refresh behavior, and renders the existing generated-file metadata supplied by Phase 10R.

```text
Persisted Record → latest completed ValidationRun → authorized results API
      → typed Phase 9 workspace → real records, metrics, validation, pagination, files
```

The API returns normalized requested field values only. It does not expose raw field evidence, provenance, browser state, page HTML, storage keys, credentials, or internal file paths. Every result query first uses the existing project-owner job lookup.

## Results contract

Each result item includes the durable database record UUID, optional stable record identity, normalized `data`, optional validation projection, and already-permitted source page UUID. A validation projection contains the persisted Phase 7 status (`PASS`, `FAIL`, `WARN`, `UNRESOLVED`, or `SKIPPED`), persisted quality (`HIGH`, `MEDIUM`, `LOW`, `INVALID`, or `UNRESOLVED`), and the per-record stored summary.

If no validation run has completed, `validation_available` is `false` and every item’s validation is `null`; no placeholder status is manufactured. Job-wide metrics use the authoritative completed validation-run summary, not the current page of rows.

## UI behavior

The established Data Loom composition and artifact list remain unchanged. The results table derives its columns from returned record values, renders values as React text, shows the actual validation state/quality, and uses the existing bounded API pagination. It distinguishes loading, API failure, and completed jobs with no persisted records. Page refresh restores the job reference from `?job=` and reloads the authorized API data.

## Verification and boundary

Focused tests seed only test-database records with durable Phase 7 outcomes, then verify real value projection, all validation status categories, job-wide metrics, different pagination pages, validation absence, and cross-user denial. Frontend view-model and server-rendered component tests verify the real display, empty state, and safe error state without production sample rows. The full Phase 8/10R export regressions remain in the backend suite.

> **Phase 11 and Phase 12 are not started by Phase 9R.** This repair does not change browsing, discovery, extraction, validation rules, planner behavior, document rendering, dependency posture, deployment, infrastructure, or production credentials.

# Phase 7 — Validation Engine

## Purpose and boundary

Phase 7 evaluates immutable Phase 6 candidate records against the immutable Phase 4 canonical plan. It creates durable, versioned validation results; it does not alter a raw value, normalized value, extraction evidence, provenance, discovery inventory, or canonical plan.

> Extraction says a value was found. Validation says whether that stored candidate satisfies deterministic rules. Phase 7 never repairs data to make a rule pass.

Validation starts from `VALIDATING` and finishes at `READY_FOR_EXPORT`. This is a handoff state only: **Phase 8 exports are not implemented and no file is generated.**

## Architecture and persistence

| Boundary | Responsibility |
| --- | --- |
| `ValidationService` | Deterministically evaluates in-memory immutable record payloads using a stable rule order. It has no browser, network, model-provider, exporter, or database dependency. |
| `JobService` | Creates a versioned validation run, claims it through the durable worker/outbox path, persists results, emits ordered events, handles cancellation/retry, and moves the job to the export-ready handoff. |
| `validation_runs` | Append-friendly audit entity with run number, operation key, schema/ruleset version, plan version, status, timestamps, and bounded summary. |
| `validation_results` | One immutable result per `(validation_run_id, record_id)`, with status, quality, plan/rule/schema versions, field/record findings, and summary. |

Migration `0006_validation_runs` adds the run table and extends the existing result table. Revalidation is represented by a new run number and new result rows; completed results are never overwritten.

## Rule registry and outcomes

The baseline registry is deterministic and versioned as `rules.v1`. Current rule order is required/presence, declared type, supported format, raw-to-normalized consistency, evidence, provenance, then narrowly named cross-field relationships. Rules return only `PASS`, `FAIL`, `WARN`, `UNRESOLVED`, or `SKIPPED` with concise safe messages.

| Rule group | Current behavior |
| --- | --- |
| Required and missing | Missing required values fail. Missing optional values warn rather than silently becoming values. |
| Type and format | Checks declared string/text, numeric/currency, boolean, URL, email, ISO date, and ISO datetime representations. Non-finite numbers fail. |
| Normalization | Re-applies the documented safe Phase 6 normalization to raw text and compares it with the stored normalized candidate. It never rewrites either value. |
| Evidence | Requires an evidence location and bounded source snippet when evidence is supplied; absent evidence is a warning. |
| Provenance | Requires a page identifier and matching canonical plan version. |
| Cross-field | Applies only explicit names: `start_date ≤ end_date`, `min_price ≤ max_price`, and `discounted_price ≤ original_price`. |

The baseline does not make network requests, browse pages, invoke Playwright, perform semantic AI validation, run arbitrary SQL, or execute user/model content.

## Quality classification

Quality is deterministic, not a probability. Any `FAIL` yields `INVALID`; otherwise any `UNRESOLVED` yields `UNRESOLVED`; otherwise warnings yield `MEDIUM`; and fully passing records yield `HIGH`. `LOW` is reserved for future documented, deterministic partial-record policy and is not used as a fabricated score.

## Durability, idempotency, cancellation, and retry

Extraction creates a `run_validation` outbox command with stable job, run, operation, and attempt identifiers. A completed run is not claimed again, and the database uniqueness constraint prevents a duplicate result for the same run/record. Validation checks cancellation before claim and between records; already stored results remain auditable. Only infrastructure-class failures are retryable; a record that fails deterministic validation is a persisted result, never a retry reason.

Relevant events include `validation_started`, `record_validation_completed`, `validation_retry_scheduled`, `validation_failed`, and `validation_completed`. Event payloads contain only bounded identifiers, status, counts, and safe codes.

## Testing and limitations

Focused tests cover valid data, required and optional missing fields, invalid currency/URL, evidence warnings, normalization inconsistency, immutable input behavior, and quality precedence. The full backend and frontend regression suites remain required gates.

The current baseline intentionally omits broad natural-language semantic rules, locale-aware business constraints, distributed cross-page conflict correlation, final user-facing validation dashboards, and exporter behavior. It also does not equate format/type success with factual correctness.

## Phase 8 boundary

**Phase 8 — Excel / CSV / JSON was not started.** `READY_FOR_EXPORT` means validated internal results are available for a future exporter; it does not create `.xlsx`, `.csv`, JSON export files, downloads, formatting pipelines, or any final results UI.

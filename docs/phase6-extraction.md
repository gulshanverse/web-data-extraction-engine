# Phase 6 — Extraction Engine

## Purpose and boundary

Phase 6 converts **visited Phase 5 inventory pages** into durable, evidence-backed candidate records according to the immutable Phase 4 `plan.v1`. It never discovers a URL, alters the canonical plan, decides whether a value is correct, creates validation findings, or generates files.

> Extraction answers “What structured records can be extracted according to the canonical plan?” Phase 7 will decide whether those records are valid.

The durable lifecycle now proceeds from `DISCOVERING` to `EXTRACTING`, and, after all extraction work is persisted, transitions to `VALIDATING` as a handoff state. No validation command, rule, score, status, or implementation is introduced in this phase.

## Architecture

| Boundary | Responsibility |
| --- | --- |
| Existing browser engine | Navigates only an existing page-inventory URL under the Phase 3 policy, then returns a bounded inert rendered-document signal. |
| Browser contract | Returns bounded text, JSON-LD script text, OpenGraph metadata, tables, and repeated semantic block signals. It makes no strategy decision and creates no record. |
| `ExtractionService` | Applies deterministic strategy priority, maps **only requested plan fields**, normalizes values safely, creates missing-field representations, assigns identity, and builds bounded evidence. |
| `JobService` | Claims one visited inventory page, persists candidate records transactionally, updates extraction page metadata, appends events, schedules the next extraction page through the durable outbox, and handles retry/cancellation. |
| Existing records API | Returns the existing `records` payload projection; no results UI or export route is added. |

## Strategy priority

The order is deterministic: **structured data**, then **tables**, then **repeated blocks**, then a single **detail-page** fallback. A lower-priority strategy is used only when the higher one does not produce a coherent record. The implementation does not use an LLM or website-specific selector database.

Structured JSON-LD is parsed as untrusted inert JSON. Arrays and `@graph` entities are supported; malformed JSON-LD adds a bounded extraction warning and never executes. OpenGraph may supply detail-page candidates. Table extraction uses header-to-requested-field mapping and keeps every row together. Repeated-block extraction retains each observed container separately; it does not globally merge matching values across blocks.

## Field mapping and normalization

Every output field originates from a Phase 4 field definition. Matching uses the stable field name, label, and aliases; unrequested page fields are ignored. Each stored field retains its raw text, safe normalized candidate, declared type, strategy, extraction confidence, missing flag, and bounded evidence.

| Declared type | Safe normalization behavior |
| --- | --- |
| `string`, `text` | Collapses whitespace without changing content semantics. |
| `integer`, `number`, `currency` | Parses a bounded numeric token; malformed values remain unresolved. |
| `boolean` | Recognizes only a small documented literal vocabulary. |
| `date`, `datetime` | Accepts ISO-format values only. |
| `url` | Resolves a relative value against the already policy-checked page URL; it does not navigate to it. |
| `email` | Extracts a bounded syntactically plausible address. |

Missing data is stored as `null` with `missing: true`. It is never substituted with an invented default and is not marked valid or invalid.

## Record schema, identity, provenance, and evidence

Stored payloads use `records.v1` and include only candidate fields plus provenance. Migration `0005_extraction_records` extends the existing `records` table with `record_identity`, plan version, strategy, provenance, and bounded extraction metadata. A unique `(job_id, record_identity)` constraint makes duplicate delivery idempotent.

The current identity is SHA-256 over page ID, canonical page URL, and the ordered requested-field candidate values. This intentionally favors safe duplicate suppression inside a job over speculative cross-page merging. Provenance includes source/canonical URL, page ID, plan version, strategy, and extraction timestamp supplied by the database. Evidence contains only a truncated source-text snippet and a static container/row/structured-data location; it never includes full HTML, browser storage, cookies, headers, or credentials.

## Limits, retries, and cancellation

| Setting | Default | Effect |
| --- | ---: | --- |
| `EXTRACTION_MAX_RECORDS` | 10,000 | Server-owned cap combined with the immutable plan record cap. |
| `EXTRACTION_MAX_EVIDENCE_CHARS` | 500 | Maximum stored evidence snippet length per field. |
| `EXTRACTION_MAX_DOCUMENT_CHARS` | 200,000 | Browser-side bound on rendered text. |
| `EXTRACTION_MAX_DOCUMENT_ITEMS` | 500 | Bound on JSON-LD scripts, tables, rows, and repeated blocks returned to extraction. |
| `EXTRACTION_MAX_RETRIES` | 2 | Bounded retry budget for transient browser failures. |

The existing browser policy remains responsible for scheme, DNS/IP, redirect, resource, response-size, timeout, and browser-capacity limits. There is no direct HTTP extraction path. Cancellation is checked before page claim, during browser navigation through the existing probe, and before record persistence or new work scheduling. Transient browser failures retry through the existing durable retry mechanism; policy blocks, unsupported input, missing values, malformed data, and cancellation do not retry.

## Security and hallucination protection

There is no AI-assisted extraction in Phase 6. The engine is deterministic and never generates or executes page-derived code, model-generated code, selectors, scripts, shell commands, filesystem paths, or arbitrary navigations. JSON-LD is parsed only as data. The browser’s static internal document-signal collector is the only DOM-inspection implementation and is bounded before the extraction domain receives it.

## Testing and known limitations

Focused tests cover JSON-LD, nested structured values, malformed JSON-LD warnings, tables, repeated-record boundaries, detail records, missing fields, currency/boolean/URL normalization, evidence preservation, identity, transactional persistence, duplicate-safe persistence, cancellation, retry, and the absence of validation results. All prior backend and frontend regressions remain part of the quality gate.

The initial deterministic engine does not include a semantic AI fallback, broad natural-language date parsing, locale-aware currency parsing, dynamic infinite-scroll extraction, page screenshot/OCR interpretation, site-specific selectors, or cross-page semantic record merging. It records unresolved/missing candidate values rather than fabricating them.

## Phase 7 boundary

**Phase 7 — Validation was not started.** The Phase 6 handoff state is `VALIDATING`, but no validation worker, quality score, validation status, business rule, cross-record check, or export implementation exists in this phase.

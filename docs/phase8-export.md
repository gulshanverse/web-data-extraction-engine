# Phase 8 — Excel / CSV / JSON Export Engine

## Purpose and boundary

Phase 8 converts a **validated internal dataset** into deterministic CSV, JSON, or XLSX bytes. The shared canonical dataset is the only input to every writer. Export code does not browse, discover, extract, normalize, validate, modify source records, or invoke a model.

> The same canonical plan field order and selected validation-record policy feed every format writer; output differences are limited to format representation.

Only `xlsx`, `csv`, and `json` are supported. PDF, DOCX, Markdown, TXT, HTML reports, presentation files, results UI work, and deployment are outside Phase 8.

## Canonical dataset and policies

`build_dataset` takes the plan field order, a validation run identity, selected immutable record views, and explicit export options. It emits one ordered row representation. Unrequested fields cannot enter an export. Rows are ordered by stable record identity, and fields follow the canonical plan rather than alphabetical order.

| Policy | Included records |
| --- | --- |
| `ALL_RECORDS` | Every supplied validated-record view, preserving its validation metadata if selected. |
| `VALID_ONLY` | Only `PASS` validation status. |
| `VALID_AND_WARNINGS` | `PASS` and `WARN`, excluding failing/unresolved records. |

Null remains `null` in JSON and an empty field/cell in CSV/XLSX. Nested list or object values serialize as compact, sorted JSON text in spreadsheet formats. Unicode is emitted as UTF-8 for CSV/JSON and preserved by XLSX.

## Writers and security

| Writer | MIME type | Key behavior |
| --- | --- | --- |
| CSV | `text/csv` | Uses Python’s CSV module, UTF-8, LF row terminators, header row, escaping, and deterministic field order. |
| JSON | `application/json` | Uses a documented `export.v1` envelope with ordered fields, count, plan/run metadata, and records. |
| XLSX | Office Open XML spreadsheet MIME type | Produces a `Data` worksheet with bold headers, frozen header row, filter, constrained column widths, and optional concise validation summary. |

Spreadsheet-cell values beginning (after leading whitespace) with `=`, `+`, `-`, or `@` receive a leading apostrophe in CSV/XLSX output. This protects common spreadsheet applications from unintended formula execution while retaining the original visible text. JSON remains structural data and is not altered by this spreadsheet-only policy.

The existing `LocalArtifactStore` accepts the XLSX MIME type and the `store_export` helper writes an already-built export through that storage abstraction. Storage keys remain generated opaque keys; no caller supplies a filesystem path or filename.

## Limits and limitations

The canonical dataset builder accepts a server-owned record ceiling and fails safely when exceeded. Artifact storage applies its existing byte ceiling. The current baseline is deliberately small and deterministic: it does not yet create user-facing download routes, export UI, or later-phase document formats. Worker/API persistence integration uses the established `ExportJob` and artifact conventions in subsequent orchestration work; writer code itself remains pure and receives only canonical validated input.

## Testing

Focused tests cover field/row consistency, validation policy filtering, immutability, Unicode, nulls, nested values, formula-like values, CSV parse round-trip, JSON parse round-trip, XLSX reopenability, field order, frozen headers, and empty datasets. These tests are format-agnostic at the dataset layer and verify that all writers consume the same row representation.

## Phase 9 boundary

**Phase 9 was not started.** This phase supplies no results dashboard, export-management UI, new progress UX, or advanced result browsing.

# Phase 10 — PDF / DOCX / Other Document Formats

## Purpose and boundary

Phase 10 turns the existing Phase 8 canonical validated dataset into **human-readable documents**. The document system consumes no raw extraction page content, invokes no browser, crawler, Playwright, planner, or validator, and never changes a record value.

> Document generation is a deterministic representation of an already validated dataset, not an opportunity to reinterpret or enrich it.

## Canonical document model

`document.v1` is represented by `CanonicalDocument`, built once from `CanonicalExportDataset`. The document profile defines a safe static title, null representation (`—`), and controlled validation/provenance inclusion flags. Every renderer receives the same plan-ordered fields and rows.

| Format | MIME type | Representation |
| --- | --- | --- |
| PDF | `application/pdf` | A4/landscape table document with title, summary, repeated headers, multi-page table handling, and an empty-report message. |
| DOCX | Office Open XML Word document | Heading, metadata paragraph, canonical table, or empty-report message. |
| Markdown | `text/markdown` | Compact summary and escaped canonical table. |
| TXT | `text/plain` | Plain readable adaptation of the same summary and rows. |
| HTML | `text/html` | Standalone escaped document with no scripts, user templates, or user CSS. |

## Deterministic policies

All formats preserve canonical Phase 4 field ordering and the selected Phase 8 validation-record policy. Nulls become `—` in human-readable output. Nested lists and objects become compact, sorted JSON text; no value is silently lost. A server-provided record limit is checked before rendering. Empty documents remain valid and state `No records found.` rather than fabricating a record.

## Safety

All source-derived strings are treated as inert data. HTML uses escaping; Markdown escapes table delimiters; PDF/DOCX use text-flow APIs rather than template execution. Values such as `<script>`, `javascript:`, `{{template}}`, `${expression}`, formula-like content, and traversal-looking strings are never executed, fetched, or interpreted as paths.

The profile, templates, and style are application-owned code. There are no user-uploaded templates, arbitrary CSS, arbitrary JavaScript, arbitrary filesystem paths, shell commands, or LLM document generation.

## Unicode and layout

The baseline uses standard renderer text flow for Unicode-capable strings and verifies multilingual source strings in renderer tests. PDF selects landscape deterministically when more than five fields are present, repeats table headers across page breaks, wraps content through ReportLab paragraphs, and emits an A4 report with restrained formatting. DOCX uses the library document/table model rather than manual OOXML.

## Storage and lifecycle

The document renderers are pure byte renderers and use the existing `LocalArtifactStore` integration boundary from Phase 8 for persisted artifacts. They do not introduce another file store or expose filesystem paths. Phase 10R wires document formats into the same durable export command, worker, `GeneratedFile`, authorization, cancellation, retry, and safe download lifecycle as CSV/JSON/XLSX; render failures are deterministic failures and do not call a website or model.

## Testing and limitations

Focused tests verify PDF and DOCX reopenability, title/summary/table values, Markdown/TXT/HTML consistency, HTML escaping, null values, nested data, empty documents, and safe inert content. Existing XLSX/CSV/JSON tests remain regression coverage.

The initial implementation does not add user templates, arbitrary style customization, PDF OCR, visual/chart generation, document splitting, deployment, or broader Phase 11 security work. No attempt is made to turn untrusted URLs into executable links.

## Phase 11 boundary

**Phase 11 — Security + Testing was not started.** The Phase 10R repair is limited to durable export lifecycle controls required for deterministic formats; it does not claim broader platform hardening.

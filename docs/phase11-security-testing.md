# Phase 11 — Security + Testing

## Verification matrix

| Area | Coverage |
| --- | --- |
| Unit | URL parsing, browser policy, spreadsheet escaping, document escaping, planner schema, rate limiter, Redis DSN parsing |
| Integration/API | Input limits, safe errors, authorization/IDOR concealment, results, files, downloads, pagination, idempotency, cancellation, SSE authorization |
| Worker/recovery | Durable outbox delivery, duplicate delivery, expired lease recovery, bounded retry classification, cancellation, storage finalization cleanup |
| Browser/discovery | Private resolution, redirect/resource checks, response/download ceilings, scope/depth/link/sitemap limits, cancellation paths |
| Export/document | Canonical validated dataset only, CSV/XLSX formulas, PDF/DOCX/HTML/Markdown/TXT inert values, nulls, Unicode, output ceilings |
| Frontend | React text output for untrusted results, real validation outcomes, empty/error states, typed API client, lint/type/build regression |
| Supply chain | Python compatibility check, Node production audit, patched transitive PostCSS/Sharp graph |

## Adversarial scenario

The test suite composes the same production boundaries independently: unsafe URL forms are denied before job creation; planner tests reject policy-changing/malformed output; discovery/browser policy reject out-of-scope or private navigation; extraction/validation preserve values as data; spreadsheet writers escape formula prefixes; document renderers escape HTML/script-looking content; owner joins deny other-user results/files; and React renders returned values as text. No test makes a website value executable.

## Performance and accessibility

Server-owned limits cap request bytes, pages, records, field counts, evidence/document size, response/download size, export bytes, browser contexts, timeouts, retries, and concurrency. The database-backed regression suite exercises record counts and export ceilings without weakening limits. The existing frontend maintains semantic buttons, labels, table headers, status/alert roles, keyboard-reachable controls, and light/dark themes; no Data Loom redesign was made.

## Boundary

Phase 11 does not deploy infrastructure, configure production credentials, add runtime authentication, introduce new extraction/discovery/planner/export capabilities, or redesign the user interface. **Phase 12 was not started.**

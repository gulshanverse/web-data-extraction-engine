# Phase 9 — Progress + Results Experience

## User journey

The Data Loom workspace now starts a real backend job, stores its stable job reference in the browser URL, restores the same job after refresh, and renders the actual lifecycle status through the established visual composition. The existing light/dark token system, navigation, job form, operation thread, results workspace, and runs ledger remain recognizable.

## API and SSE integration

The typed frontend client owns calls to the existing job creation, status, cancellation, paginated results, file listing, and SSE event endpoints. The workspace hook is the sole lifecycle adapter for the page: it maps backend states to existing Data Loom stage labels, refreshes bounded job status on SSE messages, closes connections on terminal states, and refreshes status after a transient connection error. It does not fabricate progress.

## Security and resilience

The UI renders backend messages and extracted values as React text, not injected HTML. URLs, job identifiers, operation keys, storage keys, credentials, raw prompts, and stack traces are not exposed as primary content. Cancellation invokes the existing backend endpoint and refreshes its response rather than applying a client-only terminal state.

## Boundary

Phase 9 connects the already-built pipeline to the frontend. It does not add document generation, PDF, DOCX, Markdown, TXT, exporters, browser automation, discovery, extraction, validation rules, deployment, or a new frontend framework.

## Known limitations

The current backend development principal remains the authorization seam used by the API. The workspace uses the existing result/files endpoints and intentionally does not invent unsupported export-creation or signed-download routes. Rich record-table pagination, filtering, sorting, and an export-management panel depend on those backend contracts being completed as independently durable Phase 8/9 API operations.

# API Contracts

## Contract status

These are Phase 0 contracts for the future FastAPI implementation. They define request and response shapes without implementing the complete API. JSON examples are illustrative and use UUID job identifiers.

## API conventions

The API is versioned under `/api`. JSON requests and responses use `Content-Type: application/json`. Timestamps are RFC 3339 UTC strings. Clients must treat unknown response fields as forward-compatible additions. A request may include `Idempotency-Key` for create and command operations; the server stores the key within the authenticated project scope and returns the original result for a safe retry.

Authentication is a placeholder in Phase 0. Future requests will require an authenticated user or service identity, with authorization checked against project ownership and job membership. No browser credentials or third-party secrets are accepted through these endpoints.

## Job creation

### `POST /api/jobs`

Creates a queued extraction job and schedules planning. It does not navigate to the supplied URL synchronously.

Request:

```json
{
  "project_id": "8cc5ed8e-5bd8-4b20-9c0a-c5f8b4af3b12",
  "source_url": "https://example.com/products",
  "task": "Extract all products with name, price, rating, category, and product URL.",
  "fields": ["name", "price", "rating", "category", "url"],
  "options": {
    "max_pages": 20,
    "max_records": 1000,
    "follow_pagination": true,
    "follow_relevant_links": false,
    "extract_images": false,
    "deduplicate": true,
    "validate": true
  },
  "output_formats": ["json", "csv"]
}
```

Response `202 Accepted`:

```json
{
  "job_id": "b3d7b6db-8b8c-4ed1-8d6e-4b4f8eb0f5d7",
  "project_id": "8cc5ed8e-5bd8-4b20-9c0a-c5f8b4af3b12",
  "status": "QUEUED",
  "progress": {
    "percent": 0,
    "stage": "QUEUED",
    "message": "Job accepted"
  },
  "created_at": "2026-01-01T12:00:00Z"
}
```

The server validates URL syntax, scheme, initial policy, request limits, supported formats, and project authorization before creating the job. Detailed URL security is specified in [Security Boundaries](security-boundaries.md).

## Job status

### `GET /api/jobs/{job_id}`

Returns a status projection suitable for polling and progress display.

```json
{
  "job_id": "b3d7b6db-8b8c-4ed1-8d6e-4b4f8eb0f5d7",
  "status": "EXTRACTING",
  "progress": {
    "percent": 62,
    "stage": "EXTRACTING",
    "pages_discovered": 12,
    "pages_processed": 8,
    "records_found": 438,
    "records_valid": 421,
    "updated_at": "2026-01-01T12:04:30Z"
  },
  "plan": {
    "version": 1,
    "status": "ACTIVE"
  },
  "error": null,
  "created_at": "2026-01-01T12:00:00Z",
  "started_at": "2026-01-01T12:00:04Z",
  "completed_at": null
}
```

Progress is an estimate, not a guarantee. The API exposes counts only when available and must not claim completion based solely on queue acknowledgement.

## Cancellation

### `POST /api/jobs/{job_id}/cancel`

Requests cooperative cancellation. The endpoint is idempotent: cancelling an already cancelled job returns its current state, while cancelling a completed job is rejected as a conflict.

Response `202 Accepted` while cancellation is being processed:

```json
{
  "job_id": "b3d7b6db-8b8c-4ed1-8d6e-4b4f8eb0f5d7",
  "status": "CANCELLED",
  "cancelled_at": "2026-01-01T12:05:00Z"
}
```

## Results

### `GET /api/jobs/{job_id}/results`

Returns validated structured records with pagination. The response includes the active plan version, result schema version, total count when available, and validation summary.

```json
{
  "job_id": "b3d7b6db-8b8c-4ed1-8d6e-4b4f8eb0f5d7",
  "plan_version": 1,
  "schema_version": "records.v1",
  "items": [
    {
      "record_id": "f2862bf6-87ef-4a41-b19a-31d9d1cc8cf5",
      "data": {
        "name": "Example product",
        "price": "19.99",
        "rating": 4.5,
        "category": "Demo",
        "url": "https://example.com/products/example"
      },
      "validation": "PASSED",
      "source_page_id": "e1dc3030-e3dc-4e85-a6d8-0a6cc1a25e8d"
    }
  ],
  "page": 1,
  "page_size": 100,
  "total": 1,
  "validation_summary": {
    "passed": 1,
    "warnings": 0,
    "failed": 0
  }
}
```

Results are unavailable or incomplete while a job is in an earlier stage. A cancelled or failed job may return partial results only when the API contract and authorization allow it.

## Generated files

### `GET /api/jobs/{job_id}/files`

Returns metadata and authorized download links for generated artifacts. Links should be short-lived and scoped to the authenticated user or project.

```json
{
  "job_id": "b3d7b6db-8b8c-4ed1-8d6e-4b4f8eb0f5d7",
  "files": [
    {
      "file_id": "15bdf5d1-0e4b-4b14-835f-91e7b5dbf8db",
      "format": "csv",
      "media_type": "text/csv",
      "byte_size": 48210,
      "checksum": "sha256:...",
      "download_url": "https://api.example.invalid/download/temporary-token",
      "expires_at": "2026-01-01T13:00:00Z"
    }
  ]
}
```

## Error schema

All errors use a stable shape:

```json
{
  "error": {
    "code": "DOMAIN_NOT_ALLOWED",
    "message": "The requested domain is not permitted by the project policy.",
    "retryable": false,
    "correlation_id": "9f6e2c57-f7ef-42a7-9f80-08a1c424f0e4",
    "details": {}
  }
}
```

`details` contains safe, documented fields only. It must not expose credentials, cookies, internal network addresses, stack traces, model prompts, or raw sensitive page content. Standard HTTP mapping is `400` for malformed requests, `401` for missing authentication, `403` for authorization or policy denial, `404` for inaccessible resources, `409` for illegal state conflicts, `413` for size limits, `422` for schema validation, `429` for rate limits, and `500`/`503` for safe server or dependency failures.

Canonical domain error codes include `INVALID_URL`, `DOMAIN_NOT_ALLOWED`, `BROWSER_TIMEOUT`, `PAGE_LOAD_FAILED`, `DISCOVERY_FAILED`, `EXTRACTION_FAILED`, `VALIDATION_FAILED`, `EXPORT_FAILED`, `JOB_CANCELLED`, `RESOURCE_LIMIT_EXCEEDED`, `PLAN_INVALID`, `UNSUPPORTED_FORMAT`, `NOT_AUTHORIZED`, and `INTERNAL_ERROR`.

## Progress transport

The first version should use **Server-Sent Events (SSE)** for job progress because progress is predominantly one-way server-to-client data, the browser client needs a simple reconnectable stream, and the command API remains ordinary HTTP. A future WebSocket channel is justified only if the product requires bidirectional interactive control or high-frequency client commands.

### `GET /api/jobs/{job_id}/events`

The endpoint returns `text/event-stream` events ordered by per-job sequence number. Clients send `Last-Event-ID` on reconnect. The server replays missed durable events when retained and then keeps the stream open until completion, cancellation, failure, or timeout.

Example:

```text
event: records_found
id: 18
data: {"job_id":"b3d7b6db-8b8c-4ed1-8d6e-4b4f8eb0f5d7","count":438,"occurred_at":"2026-01-01T12:04:30Z"}
```

## Contract rules

The API never accepts an instruction to bypass access controls. It does not expose internal worker commands directly. All job reads, cancellation requests, results, and files are authorized against the authenticated project. Schema and route changes require versioning or a compatibility plan before implementation.

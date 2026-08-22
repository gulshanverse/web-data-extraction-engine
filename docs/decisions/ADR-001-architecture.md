# ADR-001: Modular Asynchronous Architecture

- **Status:** Accepted for Phase 0
- **Date:** 2026-08-22
- **Decision owners:** Project maintainers

## Context

The AI Web Data Agent must turn a user’s URL and natural-language extraction intent into structured, validated data and optional exports. The platform will encounter dynamic pages, long-running crawls, partial failures, untrusted content, variable result sizes, and future output formats. A single synchronous scraper or a giant AI agent would make security, retries, testing, and independent evolution difficult.

## Decisions

### 1. Use a modular monorepo

The repository will keep the web client, API, shared contracts, domain modules, workers, tests, and documentation in one repository during early development. Logical boundaries are explicit even when local development runs fewer processes. This reduces coordination overhead while preserving a path to independently scaled workers.

### 2. Use Next.js and TypeScript for the client

The frontend direction is Next.js with TypeScript, Tailwind CSS, and shadcn/ui. The client is responsible for request forms, job status, progress, results, and file links. It does not receive browser credentials or execute extraction logic.

### 3. Use FastAPI and Python for the API and data plane

FastAPI provides typed HTTP contracts and asynchronous request handling. Python is the backend language because the planned data-processing ecosystem includes Playwright, Pandas, BeautifulSoup4, lxml, and OpenPyXL. Dependencies are introduced in later phases when functionality is implemented.

### 4. Use asynchronous Playwright workers

Browser automation is isolated from the API and runs asynchronously under an explicit browser policy. Per-job contexts, bounded actions, cancellation, and resource limits are necessary for dynamic sites and safe concurrency. Browser automation is not controlled directly by the planner model.

### 5. Use PostgreSQL as the system of record

PostgreSQL stores users, projects, sources, jobs, plan versions, page metadata, records, validation results, export jobs, generated-file metadata, and progress events. It supports durable state transitions, authorization scopes, querying, indexing, and auditability.

### 6. Use Redis for queue transport and coordination

Redis provides a lightweight background-job transport for local development and early deployments. Queue delivery is treated as at least once; durable job state and operation markers remain in PostgreSQL. A future deployment may replace or extend queue technology without changing domain contracts.

### 7. Use an object-storage abstraction

A typed storage port separates snapshots and generated files from extraction logic. The local implementation uses the filesystem during development. A later S3-compatible implementation can provide scalable storage, signed URLs, encryption, and lifecycle rules without changing domain modules.

### 8. Use an explicit plan hand-off between AI and deterministic execution

The Planner Agent outputs a versioned schema-validated plan. Browser, discovery, extraction, validation, and export components consume that plan through typed contracts. This preserves AI flexibility while keeping execution, policy enforcement, retries, and result validation deterministic.

### 9. Use SSE for first-version progress

Server-Sent Events are selected for the initial progress channel because updates are primarily server-to-client, the web browser has native support, reconnection can use `Last-Event-ID`, and commands remain ordinary HTTP requests. WebSockets remain a future option if bidirectional interactive control becomes necessary.

### 10. Enforce public, permitted-content boundaries

The platform is designed for content the user is permitted to access. URL validation, domain allowlists, SSRF defenses, redirect revalidation, worker isolation, resource budgets, authorization, and safe artifact handling are architectural boundaries. CAPTCHA solving, paywall circumvention, credential theft, authentication bypass, and anti-security evasion are explicitly excluded.

## Consequences

The design adds operational components and durable contracts compared with a simple scraper, but it enables asynchronous execution, worker scaling, safe cancellation, replayable progress, independent exporters, and testable boundaries. PostgreSQL and Redis introduce deployment dependencies; Docker Compose can make local development reproducible. The planner cannot directly improvise browser behavior, so plan schemas and later repair policies must be designed carefully.

## Alternatives considered

| Alternative | Reason not selected |
|---|---|
| Single synchronous scraper | Poor fit for long jobs, dynamic pages, retries, progress, and isolation |
| Giant autonomous AI agent | Unsafe and difficult to test; mixes intent, access, extraction, and output concerns |
| WebSockets as the first progress channel | More bidirectional complexity than needed for one-way progress |
| Filesystem paths inside extraction code | Prevents S3 migration and weakens ownership and access controls |
| Queue as source of truth | Queue delivery is not durable domain state and may be at-least-once |
| Separate repositories immediately | Adds release and contract coordination overhead before the boundaries stabilize |

## Revisit triggers

This decision should be revisited when multi-region execution, high-volume queueing, interactive browser control, a different identity architecture, or compliance requirements exceed the assumptions of the initial deployment. Any change must preserve the public-content boundary, storage abstraction, plan hand-off, and durable job lifecycle unless a new ADR explicitly replaces them.

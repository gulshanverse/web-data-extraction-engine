# Phase 5 — Discovery Engine

## Purpose and boundary

Phase 5 answers **which policy-compliant pages and URLs should be considered for later extraction**. It reads the immutable Phase 4 `plan.v1` and persists a deduplicated page inventory. It does not produce field values, business records, selectors, XPath, validation findings, datasets, or exports.

> Discovery can inspect transient navigation metadata and bounded sitemap text. It never persists arbitrary page HTML or turns page content into structured records.

The worker lifecycle is `BROWSER_INITIALIZING → DISCOVERING`. When no further inventory pages remain, the job stays in `DISCOVERING` with a durable `discovery_completed` event; Phase 5 deliberately does not enqueue or implement Phase 6 extraction.

## Architecture

| Boundary | Responsibility |
| --- | --- |
| `DiscoveryService` | Deterministically normalizes URLs, applies scope, classifies pagination/relevant links, and parses bounded sitemap locations. It has no database or browser dependency. |
| Existing browser engine | Performs all navigational I/O, DNS/redirect/resource policy enforcement, cancellation polling, context capacity control, and bounded transient navigation-signal collection. |
| `JobService` | Claims one durable inventory page, persists candidate metadata idempotently, emits ordered events, schedules the next discovery page through the existing outbox, and handles failure/cancellation. |
| `pages` table | Is the durable page inventory. It retains URL metadata, state, depth, parent, source method, scope decision, relevance metadata, and observed navigation metadata; it has no page-body column. |
| Existing API | Exposes a protected paginated `GET /api/jobs/{job_id}/pages` projection. It does not expose worker commands or page content. |

## Inventory and states

The `pages` table retains its existing unique `(job_id, canonical_url)` constraint. Migration `0004_discovery_inventory` extends it with discovery-specific metadata: `discovered_via`, `depth`, `parent_page_id`, `deduplication_key`, `policy_decision`, relevance metadata, safe discovery metadata, and `visited_at`.

The controlled Phase 5 inventory vocabulary is `DISCOVERED`, `QUEUED`, `VISITED`, `REJECTED`, `DUPLICATE`, `FAILED`, and `SKIPPED`. Existing source-page capture becomes inventory entry depth zero. No `records` rows are created by discovery.

## URL normalization and deduplication

`canonicalize_url` resolves relative, root-relative, and absolute navigation links against the current page; lowercases schemes and hosts; removes fragments; elides default ports; normalizes dot path segments and percent encoding; and preserves query strings. It rejects missing hosts, credential-bearing URLs, malformed ports, and all unsupported schemes including `javascript:`, `data:`, `file:`, `ftp:`, `blob:`, `mailto:`, and `tel:`.

Canonical URL identity, not raw-string equality, drives deduplication. A duplicate does not create another inventory entry; a safe `page_duplicate` event records the fact.

## Scope and subdomains

The default server-side policy is `SAME_ORIGIN`: scheme, hostname, and effective port must match the plan source. `SAME_SITE` and `EXPLICIT_ALLOWED_DOMAINS` are available as controlled configuration modes. Same-site mode uses a conservative two-label approximation and must not be read as public-suffix-aware domain ownership. Same-origin is therefore the recommended default. A source plan never overrides the server’s scope or page ceilings.

Browser-level URL, DNS/IP, redirect, scheme, resource-type, response-size, timeout, cancellation, and context-capacity controls remain exclusively in the Phase 3 browser engine. Discovery does not create a weaker navigational HTTP path.

## Links, pagination, relevance, and sitemap handling

The browser returns only bounded anchor metadata (`href`, text, `rel`, and `aria-label`) when a discovery operation requests navigation signals. `DiscoveryService` classifies observed `rel=next`, next-labelled, and evidenced pagination signals without guessing URLs. Relevant links receive an explainable deterministic ranking based on plan-summary keyword overlap and same-scope navigation metadata; no additional model is called.

Sitemap support is opt-in. When `DISCOVERY_ENABLE_SITEMAPS=true`, the depth-zero source may enqueue a same-scope `/sitemap.xml` inventory page. That page is navigated through the same browser policy, and only bounded transient XML text is parsed for `<loc>` URLs. Nested sitemap URLs consume ordinary inventory depth and page budgets. Robots.txt declarations are not implemented in this phase, and the system does not claim robots-policy compliance.

## Limits, pacing, retries, and cancellation

| Setting | Default | Enforcement |
| --- | ---: | --- |
| `DISCOVERY_MAX_PAGES` | 100 | Authoritative inventory cap, also constrained by the immutable plan page bound. |
| `DISCOVERY_MAX_DEPTH` | 2 | Candidate depth cap. |
| `DISCOVERY_MAX_LINKS_PER_PAGE` | 200 | Bounds transient anchor metadata analysis. |
| `DISCOVERY_MAX_CONCURRENCY` | 1 | Documents conservative discovery intent; actual browser contexts remain bounded by Phase 3 `BROWSER_MAX_CONTEXTS`. |
| `DISCOVERY_MIN_DELAY_SECONDS` | 0 | Optional cooperative pacing after a page operation. |
| Sitemap limits | 1 MiB, 500 URLs, depth 1 | Bound transient sitemap parsing and traversal. |

Only transient browser timeout/navigation/browser failures are retryable. Policy denials, scope denials, unsupported URLs, page limits, and cancellation are terminal. Retries use existing durable job attempts and exponential-backoff behavior. Cancellation is checked before claim, during the browser navigation, and before persistence; it prevents scheduling new inventory work.

## Events and durability

Discovery reuses the ordered `progress_events` store. Relevant events include `discovery_started`, `page_queued`, `page_visited`, `page_discovered`, `page_rejected`, `page_duplicate`, `pagination_detected`, `discovery_retry_scheduled`, `discovery_failed`, and `discovery_completed`. Redis remains transport only; pages, job state, events, leases, and outbox commands are durable in PostgreSQL.

Expired discovery leases are recovered through the existing recovery loop. It locates the same queued/discovered inventory page and emits a new durable `run_discovery` command instead of rerouting the job to planning.

## Testing and known limitations

Phase 5 tests cover deterministic canonicalization, unsupported schemes, conservative subdomain scope, duplicate elimination, pagination/relevance classification, scope rejection, bounded sitemap parsing, inventory persistence, event emission, retry classification, cancellation, and the explicit absence of records. Existing Phase 0–4 backend and frontend suites remain part of the regression gate.

The implementation does not include a local HTTP fixture website, robots.txt parsing, a direct HTTP sitemap fetcher, public-suffix-aware same-site scope, per-domain distributed rate limiting, adaptive infinite-scroll traversal, or general sitemap format support beyond bounded XML `<loc>` parsing through the browser boundary. These limitations are explicit; none is hidden behind an unsupported success state.

## Phase 6 boundary

**Phase 6 — Extraction was not started.** Page inventory URLs and navigation metadata may be inputs to a later extraction phase, but this phase does not inspect pages for field values or create records.

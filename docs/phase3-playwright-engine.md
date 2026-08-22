# Phase 3 — Playwright Browser Engine

## Scope

Phase 3 implements the narrow browser boundary promised by Phase 0 and Phase 2. A Redis worker receives a durable `run_browser_capture` command only after the Phase 2 deterministic draft plan has moved a job to `BROWSER_INITIALIZING`. The worker creates one isolated Chromium context and one initial page, performs a policy-controlled navigation, captures safe metadata and an optional screenshot, stores artifacts through `ArtifactStore`, appends durable events, and stops at the discovery boundary.

It does **not** interpret web content, choose links, discover pagination, select fields, create records, validate data, or generate exports.

## Ownership and lifecycle

`PlaywrightBrowserEngine` owns no global browser, page, or context. Each `capture()` invocation creates and closes its own Playwright manager, Chromium browser, context, and page in `finally` cleanup. `BrowserCapacity` is injected into the engine by worker startup and bounds concurrent contexts within that worker process. A worker operation owns its resources explicitly; the API routers and ORM models do not import Playwright.

The worker persists a lease before capture, checks the durable cancellation flag before launch and while navigation is pending, closes resources on every outcome, and clears the lease only after a safe finalization transaction. A capture records `browser_initializing`, launch/context/page, navigation, browser-complete, failure, retry, or cancellation events through the existing ordered progress-event store.

## Navigation and policy

`DefaultBrowserPolicy` accepts only canonical `http` and `https` URLs without credentials or fragments. It restricts requests to the source domain and explicit subdomains, rejects private, loopback, link-local, multicast, reserved, and unspecified DNS answers, and blocks unsupported resource types. Initial URLs and the observed redirect chain are evaluated under the policy. The initial browser request route also blocks disallowed resource requests; later Phase 11 hardening should add network-level egress controls and stricter DNS pinning to further reduce redirect/DNS-rebinding exposure.

Each operation applies configured launch, navigation, action, whole-operation, and shutdown timeouts. It bounds pages, redirects, contexts, response headers, screenshot bytes, download bytes, and browser lifetime. Popups are closed immediately. Downloads remain limited to a controlled capture helper and are stored under opaque keys; no caller supplies a filesystem path.

## Context isolation and defaults

Contexts are new per job, have no shared cookies or persistent profile, use an explicit viewport, locale, timezone, and identifiable user agent, start with no permissions, and do not receive application credentials. Headless Chromium is the default. Configuration is environment-backed in `.env.example` and bounded by `Settings` fields rather than scattered literals.

## Artifacts and metadata

Screenshots and controlled downloads are stored through `LocalArtifactStore`, which uses opaque keys, atomic writes, restrictive permissions, size bounds, checksum calculation, and cleanup of failed partial writes. The `browser_artifacts` table stores references, never raw bytes. `pages` now carries safe navigation metadata: final URL, status, content type, title, viewport, timing, redirect count, and bounded browser metadata.

## Error and retry behavior

Browser launch, crash, and navigation failures are classified as retryable where appropriate. Policy denials, resource limits, cancellation, navigation timeout, oversized artifacts, and unsupported targets are terminal or cooperative-cancellation outcomes. Public events and job errors use safe messages and stable codes; logs exclude cookies, authorization headers, credentials, and unrestricted page content.

## Local development and testing

Install dependencies with `uv pip install --system -e '.[dev]'` and Chromium with `python -m playwright install chromium`. Docker builds install Chromium with Playwright’s supported dependency installer. Apply migrations with `alembic -c services/api/alembic.ini upgrade head`, then run the API and worker as documented in the README.

Tests use a controlled local HTTP fixture plus an actual installed Chromium. They cover browser lifecycle, context capacity, navigation metadata, redirect denial, URL policy, timeout, cancellation, screenshot storage/checksum, safe download storage, oversized downloads, cleanup of partial artifacts, policy resource limits, durable orchestration, retry classification, and Phase 2 API regressions. Generated artifacts remain in temporary test storage and are not committed.

## Known limitations

This is an initial policy layer, not a claim that SSRF or hostile-site risk is fully solved. DNS answers are revalidated in policy and redirect chains are checked before persistence, but deployment-level egress filtering, DNS pinning, sophisticated response streaming limits, robots policy implementation, authorization hardening, and retention services remain future hardening work. Browser concurrency is bounded per worker process; distributed cross-worker capacity coordination is a later operational concern.

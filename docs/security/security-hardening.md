# Security Hardening Record

## Implemented in Phase 11

Phase 11 adds a server-owned maximum API request-body check, a documented bounded process-local API limiter, safe default response headers for API responses, a public-port allowlist at both initial URL admission and browser navigation, and Redis DSN propagation for username/password/TLS/database configuration. These controls preserve the existing durable architecture and do not add extraction, discovery, planning, export, UI, or deployment features.

| Control | Enforcement point | Failure behavior |
| --- | --- | --- |
| Request-size ceiling | HTTP middleware before API parsing | `413 RESOURCE_LIMIT_EXCEEDED` with safe correlation ID. |
| API request rate | HTTP middleware for `/api/*` | `429 RATE_LIMITED` plus bounded `Retry-After`. |
| Browser-safe headers | HTTP middleware | `nosniff`, clickjacking denial, referrer suppression, and API no-store caching. |
| Initial URL ports | URL admission | Rejects non-default public ports before durable job creation. |
| Browser URL ports | Navigation policy | Rejects non-default public ports on main navigation, redirects, and subresources. |
| Redis transport | ARQ DSN parser | Preserves configured `rediss`, credentials, port, and database rather than silently dropping them. |
| Dependency remediation | pnpm workspace overrides | Resolves one patched PostCSS and Sharp version across the frontend dependency graph. |

## Findings register

| Severity | Finding | Status and verification |
| --- | --- | --- |
| High | PostCSS and Sharp advisories in the baseline frontend graph | Fixed with audited patched overrides; production dependency audit reports no known vulnerabilities. |
| High | Production authentication absent | Not fixable without the Phase 12 production identity/secrets/infrastructure scope. The repository denies all development-principal resolution outside development, but production deployment remains blocked. |
| Medium | DNS rebinding cannot be completely prevented at application level after Chromium opens a socket | Application checks each URL/resource/redirect; production network egress control and resolver policy remain required. |
| Medium | Process-local rate limit is not shared across processes | Bounded single-process protection is implemented. A shared edge or Redis limiter is required before multi-instance launch. |
| Medium | Local artifact storage has no automatic retention worker or external signed URL adapter | Existing ownership checks and opaque keys remain enforced; retention/object storage are deployment prerequisites. |
| Low | ESLint runtime dependency is deprecated | Existing lint remains functional. Update with the next tested frontend toolchain refresh. |
| Informational | No GitHub Actions workflow is tracked | There is no untrusted-PR workflow exposure in this repository; CI permissions and pinned action policy are required if workflows are introduced. |

## Production-readiness assessment

**NOT PRODUCTION READY.** The code-level controls and tests are hardened, but production authentication, secret injection/rotation, network egress controls for browser/Redis/database, shared rate limiting, object storage/retention operations, observability, CI policy, and deployment validation remain outside this repository phase. Phase 12 owns those activities.

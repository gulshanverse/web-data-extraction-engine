# Production Preparation

> **Phase 12A status:** the repository is prepared for the locked topology. **No provider resource, DNS record, certificate, secret, health check, deployment, or public URL has been created or verified.** Phase 12B begins only after the account and resource prerequisites below are available.

## Target topology

| Layer | Locked provider | Repository preparation | External action still required |
|---|---|---|---|
| Static frontend, DNS, edge TLS | Cloudflare Pages and Cloudflare DNS | `apps/web` emits `out/` via `pnpm build:pages`; `_headers` is generated for Pages. | Connect the repository, create the Pages project, configure the real public build variables, bind the domain, and enable HTTPS. |
| API and worker | Oracle Always Free VM | `Dockerfile.production`, `docker-compose.production.yml`, and the host reverse-proxy template separate API from worker. | Allocate an eligible VM, install Docker and Caddy, place host secrets, configure firewall, and run migrations. |
| Auth, PostgreSQL, storage | Supabase | Cryptographic JWKS validation, `auth_subject` migration, private-storage adapter, retention job, connection pool controls. | Create one project, Auth provider, private bucket and safe service role secret storage. |
| Queue | Upstash Redis | Existing `REDIS_URL` semantics preserve `rediss://`, credentials, and database suffixes. | Create a protected TLS database and provide its URI only to the Oracle host. |
| CI | GitHub Actions | `.github/workflows/ci.yml` validates the code but has no deploy job. | Enable Actions and later create protected Phase 12B environments and secrets. |

The Pages choice is technically compatible because the current Next app generates a static export and has no server-side route requirement. Cloudflare’s documented static Pages configuration uses `next build` and an `out` directory; full SSR would instead require a Workers architecture, which this application does not need today.[1]

## Required production configuration

The API and worker receive the same server-only configuration through an Oracle-host secret file named `.env.production`. The Pages build receives only the three public `NEXT_PUBLIC_*` values.

| Category | Required variables | Placement | Notes |
|---|---|---|---|
| Application | `APP_ENV=production`, `APP_URL`, `API_URL`, `TRUSTED_HOSTS`, `APP_SESSION_SECRET` | Oracle host | Both URLs must be explicit HTTPS values; hosts and CORS wildcards are rejected. |
| Database | `DATABASE_URL`, `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_POOL_TIMEOUT_SECONDS` | Oracle host | Use Supabase SSL. A persistent IPv4-only Oracle VM should use the shared **session** pooler; migrations use the direct endpoint if IPv6 is available, otherwise the documented session pooler fallback.[2] |
| Redis | `REDIS_URL`, `REDIS_OPERATION_BUDGET_PER_MINUTE` | Oracle host | The URI must be `rediss://`; no browser ever receives it. |
| Auth | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_AUDIENCE` | Host; only URL/anon key are public to Pages | The service-role key is server-only. The API validates asymmetric signed access tokens against the project JWKS and requires issuer, audience, expiry, subject and authenticated role.[3] |
| Storage | `STORAGE_PROVIDER=supabase`, `SUPABASE_STORAGE_BUCKET`, `ARTIFACT_RETENTION_DAYS`, `ARTIFACT_CLEANUP_BATCH_SIZE` | Oracle host | Bucket stays private. The server uses opaque keys and authorized API streaming rather than raw storage URLs. |
| Frontend | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Cloudflare Pages build variables | These are intentionally public. Do not add service role, database, Redis, cookies, or JWT signing material. |

Use `sslmode=verify-full` with Supabase’s supplied CA where the selected driver/runtime supports it. Supabase documents `verify-full` as the strongest client SSL mode and its dashboard controls for enforcement.[4]

## Provider setup sequence for Phase 12B

The next phase must provision the real resources manually and record the actual identifiers in the deployment environment, never in this repository. Supabase Free currently includes two active projects, 500 MB database capacity, 1 GB storage, and pauses low-activity projects after a week; it does not include automated backups.[5] [6] The 50 MB Free per-file ceiling is a hard upper bound; `EXPORT_MAX_BYTES` is therefore limited to 50 MB and ships conservatively at 24 MiB.[7]

1. Create the Supabase project, enable database SSL enforcement, create a **private** bucket, set the global and bucket maximum file size at or below 50 MB, and retain service-role access only on the Oracle host. Private buckets enforce access control; service keys bypass RLS and must never be public.[8] [9]
2. Configure Supabase Auth with asymmetric signing keys. Set Pages as an allowed redirect origin, configure the desired email provider, and use the real project URL and publishable key as the Pages public variables. The API does not accept `X-Dev-Principal` outside development.
3. Create the Upstash database in a region near the Oracle VM and copy its TLS connection URI into the Oracle secret file. Upstash supports standard Redis clients over TLS; its free plan is constrained to 256 MB and 500,000 commands per month, so command budgets, short queues, bounded retries, and limited event polling remain mandatory.[10] [11]
4. Allocate an available Oracle Always Free Ampere A1 VM. Oracle lists Ampere A1 Compute and VCN services among Always Free offerings, but capacity is provider-controlled and accounts can be suspended for inactivity; a VM must not be assumed available.[12]
5. Create a Cloudflare Pages project from `main` with working directory `apps/web`, build command `pnpm build:pages`, and output `apps/web/out`. Configure real public build variables through the Pages dashboard rather than source control. Bind the actual frontend domain only after it exists.
6. Add the real API subdomain in Cloudflare DNS, proxy it through Cloudflare, use Full (strict) TLS with an origin certificate on the Oracle host, then add that precise frontend origin to `CORS_ALLOWED_ORIGINS` and both hosts to `TRUSTED_HOSTS`.

## Security and operations design

The production compose file intentionally runs **only** API and worker. PostgreSQL, Redis, artifact volumes, browser debugging ports, source bind mounts, reload mode, and worker ports are absent. The API binds only `127.0.0.1:8000`; the Caddy template is the single public Oracle listener. The worker retains ownership of Playwright and does not accept inbound traffic.

Configure Oracle security lists and the host firewall to permit inbound TCP 80 only for HTTP-to-HTTPS handling if required and TCP 443 only from Cloudflare’s published network ranges. Do not allow public TCP 5432, 6379, 8000, 9222, or Docker’s remote API. At the host egress layer, restrict worker traffic to DNS, package/update endpoints, Supabase, Upstash, the configured model endpoint, and public web destinations required by permitted extraction; Phase 11’s application-level DNS, private-address, redirect, port, response-size and timeout controls remain defense in depth.

Artifact cleanup is deliberately bounded and ownership-safe. Generated files plus browser screenshots/downloads receive an explicit expiry; downloads and listings exclude expired export records. The worker removes at most `ARTIFACT_CLEANUP_BATCH_SIZE` elapsed durable artifact entries per hourly run, deleting the matching object before deleting its metadata row. Failed exports are deleted immediately. An operator must inspect storage-versus-database reconciliation before any manual orphan deletion.

The static frontend uses `@supabase/supabase-js` only with public values. Requests send the short-lived access token in an `Authorization` header. Before opening `EventSource`, the frontend exchanges that verified token for an HttpOnly, Secure, same-site API session cookie; SSE then uses `withCredentials`, avoids query-string tokens, and preserves existing owner checks. Use sibling subdomains under one registrable domain to avoid third-party cookie restrictions.

## References

[1]: https://developers.cloudflare.com/pages/framework-guides/nextjs/deploy-a-static-nextjs-site/ "Cloudflare Pages: Next.js static site"
[2]: https://supabase.com/docs/guides/database/connecting-to-postgres "Supabase: Connect to Postgres"
[3]: https://supabase.com/docs/guides/auth/jwts "Supabase: JSON Web Tokens"
[4]: https://supabase.com/docs/guides/platform/ssl-enforcement "Supabase: Postgres SSL Enforcement"
[5]: https://supabase.com/pricing "Supabase pricing"
[6]: https://supabase.com/docs/guides/platform/free-project-pausing "Supabase Free project pausing"
[7]: https://supabase.com/docs/guides/storage/uploads/file-limits "Supabase Storage file limits"
[8]: https://supabase.com/docs/guides/storage/buckets/fundamentals "Supabase Storage buckets"
[9]: https://supabase.com/docs/guides/storage/security/access-control "Supabase Storage access control"
[10]: https://upstash.com/docs/redis/overall/getstarted "Upstash Redis getting started"
[11]: https://upstash.com/pricing/redis "Upstash Redis pricing"
[12]: https://www.oracle.com/cloud/free/ "Oracle Cloud Free Tier"

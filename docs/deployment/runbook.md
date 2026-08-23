# Phase 12B Deployment and Operations Runbook

> This is a **runbook for a future authorized Phase 12B operator**. It does not record a completed deployment, provider connection, health check, DNS record, or test against any external resource.

## Pre-deployment authorization gate

Do not start until an authorized operator confirms the real Cloudflare account/domain, Supabase project, Oracle tenancy/VM, Upstash database, GitHub repository settings, and secret-management locations. Capture the resource identifiers in the provider dashboards or secret manager, not in Git. The required secret **names** are `DATABASE_URL`, `REDIS_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET`, `APP_SESSION_SECRET`, `APP_URL`, `API_URL`, `CORS_ALLOWED_ORIGINS`, and `TRUSTED_HOSTS`.

## Controlled staging sequence

1. Create a staging Supabase project and a staging private bucket. Enable asymmetric JWT signing, set the real Pages staging URL as a redirect URL, enforce SSL for Postgres, and capture the correct connection string. Use a direct connection only where reachable for migrations; select session pooler mode for a persistent IPv4-only VM as documented by Supabase.[1]
2. Create the protected Upstash Redis database near the staging Oracle region. Store its TLS URI only in the staging Oracle secret file. Verify a local `rediss://` connection from the VM after firewall configuration; do not paste the command or credential into the run log.[2]
3. Allocate an Always Free Oracle VM, apply security-list and host-firewall policy, install Docker and Caddy, and install a Cloudflare Origin Certificate at the host path referenced by `infra/oracle/Caddyfile.example`. Configure Caddy as the only public listener; API must remain loopback-bound and worker remains portless.
4. Put server-only values in host-owned `.env.production` with strict file permissions. Build `Dockerfile.production`, run `docker compose -f docker-compose.production.yml up -d`, and run Alembic exactly once as a controlled admin operation before enabling application traffic.
5. Create a Cloudflare Pages staging project from this repository using `apps/web` and `pnpm build:pages`. Add only public Pages build variables. Bind the actual staging domain and set the matching exact HTTPS frontend origin in API CORS.
6. Confirm Cloudflare DNS/TLS status and exercise the controlled smoke tests below. Promote the same immutable commit only after staging evidence is recorded.

## Controlled smoke tests

| Check | Expected evidence | Stop if |
|---|---|---|
| API health/readiness | HTTPS `/health` returns healthy; `/ready` succeeds only after database and Redis checks. | TLS, database, or Redis fails. |
| Auth | Valid signed Supabase user receives owner-scoped API access; no development header works in production. | Any forged, expired, wrong-issuer, wrong-audience, or dev-header request is accepted. |
| CORS/SSE | Only configured Pages origin succeeds; credentialed EventSource gets events without a token in URL; terminal event closes. | Wildcard CORS, arbitrary origin, or query token is observed. |
| Storage | Export lands in private bucket, user downloads through `/api/files/{id}/download`, raw object path is not exposed, expiry hides the file. | Object is public or service role appears in browser assets/logs. |
| Browser | Worker processes a permitted public site; private targets and redirects remain blocked. | Worker/debug port is reachable or browser policy regresses. |
| Recovery | Worker restarts recover leases; failed export removes its partial object; retention job deletes only expired generated-file records. | Any destructive reconciliation lacks a durable ownership check. |

## Backup, restore, rollback and incident action

Free Supabase projects do not include automated database backups, so the operator must schedule and test a credential-protected logical `pg_dump` before accepting real user data.[3] Store encrypted backup outputs outside the VM, regularly test restore to an isolated staging project, and document the target data-loss window. Do not use backups, logs, CI caches, or browser storage for secrets.

For application rollback, choose the previous Git commit/image, stop API and worker gracefully, deploy the prior image, and run only migrations compatible with that release. Database downgrades need a reviewed maintenance window and a current restore point. For a suspected leaked Supabase service role, Upstash credential, database password, or session secret, immediately rotate it in the provider, replace the host secret, restart affected containers, revoke active user sessions if required, and investigate structured logs without printing credentials.

Supabase Free projects can pause after inactivity; the owner must monitor its warning email and resume a paused project through the dashboard before concluding the API is broken.[4] External monitoring is not connected in Phase 12A. Until a dedicated provider is approved, retain structured container logs, correlation IDs, and bounded health probes on the Oracle host; never log authorization headers, cookies, tokens, passwords, HTML payloads, or provider credentials.

## References

[1]: https://supabase.com/docs/guides/database/connecting-to-postgres "Supabase: Connect to Postgres"
[2]: https://upstash.com/docs/redis/overall/getstarted "Upstash Redis getting started"
[3]: https://supabase.com/pricing "Supabase pricing"
[4]: https://supabase.com/docs/guides/platform/free-project-pausing "Supabase Free project pausing"

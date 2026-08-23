# $0-First Architecture and Limits

The design is a deliberately conservative MVP topology, not a claim of unlimited capacity or high availability. It retains the user-selected providers and applies the smallest configurable operating ceilings that keep their free plans plausible.

| Provider | Role | Initial operational stance | Constraint to monitor |
|---|---|---|---|
| Cloudflare Pages | Static frontend, DNS, TLS | Static export only; external API is configured with an explicit public URL. | Pages is appropriate only while no SSR/server action is introduced. The Free plan also has build and static asset limits.[1] |
| Supabase | Auth, Postgres, private files | Two low-pool long-lived services; scheduled migration/backup discipline; explicit artifact expiration. | Free plan provides 500 MB Postgres, 1 GB storage and pauses low-activity projects after one week.[2] [3] |
| Oracle Always Free | API, ARQ worker, Chromium | One small VM with API and worker resource caps; browser concurrency one. | Shape and capacity availability vary. Oracle identifies Ampere A1 as Always Free, but allocation is not guaranteed.[4] |
| Upstash | Redis outbox/ARQ | TLS URI, `MAX_CONCURRENT_JOBS=2`, short TTLs, bounded retries, no busy polling. | Free is 256 MB / 500k commands per month; free lacks IP allow lists and ACLs, so the credential is the access boundary.[5] |
| GitHub Actions | Verification | CI only, no deploy secrets. | Cache only package-manager data; GitHub warns that cache contents can be read by pull-request users, so secrets must never be cached.[6] |

## Environment-controlled initial ceilings

| Control | Initial value | Reason |
|---|---:|---|
| `MAX_CONCURRENT_JOBS` | 2 | Preserves memory for one browser workload while keeping queue consumption bounded. |
| `BROWSER_MAX_CONCURRENCY` | 1 | Chromium is the dominant Always Free VM workload. |
| `BROWSER_MAX_CONTEXTS` | 2 | Keeps a hard in-process context ceiling. |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | 5 / 2 | Avoids consuming the small project’s connection pool across API and worker. |
| `API_RATE_LIMIT_REQUESTS` / window | 120 / 60 seconds | Keeps the existing local abuse-control ceiling while a future shared limiter is assessed. |
| `REDIS_OPERATION_BUDGET_PER_MINUTE` | 3,000 | Provides an alertable budget below the monthly command ceiling. |
| `EXPORT_MAX_BYTES` | 25,165,824 | Remains below Supabase Free’s 50 MB per-file maximum.[7] |
| `ARTIFACT_RETENTION_DAYS` / cleanup batch | 14 / 100 | Avoids unbounded storage consumption and makes deletion rate reviewable. |
| Discovery / record limits | Existing `DISCOVERY_*`, `EXTRACTION_*`, `EXPORT_*` variables | All work limits stay server-owned and environment-controlled. |

The browser worker must never be exposed as a public service. Its external egress controls complement, rather than replace, the existing Phase 11 application policy. Redis, database and Supabase service credentials never cross the static frontend boundary.

## Cost-control decision points

Review provider dashboards weekly during Phase 12B smoke testing. Pause job intake before exceeding storage, command, egress, build, or VM resource budgets. A paused Supabase Free project can be resumed within its documented restoration window, but that is an operational interruption rather than an availability feature.[3] Upstash command pressure should be reduced by preserving the transactional outbox and avoiding duplicate status/event polling.[5]

## References

[1]: https://developers.cloudflare.com/pages/platform/limits/ "Cloudflare Pages limits"
[2]: https://supabase.com/pricing "Supabase pricing"
[3]: https://supabase.com/docs/guides/platform/free-project-pausing "Supabase Free project pausing"
[4]: https://www.oracle.com/cloud/free/ "Oracle Cloud Free Tier"
[5]: https://upstash.com/pricing/redis "Upstash Redis pricing"
[6]: https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows "GitHub Actions dependency caching"
[7]: https://supabase.com/docs/guides/storage/uploads/file-limits "Supabase Storage file limits"

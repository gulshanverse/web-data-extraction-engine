# Phase 4 — AI Planner

## Purpose and boundary

Phase 4 converts an already-accepted job request into a **validated, canonical, versioned declarative plan**. It runs only through the durable `run_planning` outbox command and worker path. The planner is not invoked by an API request handler.

> **Phase 4 does not browse, fetch, crawl, inspect a DOM, use Playwright, discover links or sitemaps, choose selectors, extract records, validate records, or generate exports.**

Successful planning hands the job to the existing `BROWSER_INITIALIZING` state and emits a durable browser-capture outbox command. The existing Phase 3 browser capture stops at its own discovery boundary; **Phase 5 — Discovery has not started**.

## Architecture

| Concern | Phase 4 behavior |
| --- | --- |
| Scheduling boundary | The API creates a durable `run_planning` outbox item. The worker claims it transactionally before any provider request. |
| Model boundary | `PlannerModel` is an async provider protocol. `OpenAICompatiblePlannerModel` is the configured production implementation. `DeterministicPlannerModel` is test-only and never selected from application settings. |
| Prompt boundary | A versioned system prompt at `prompts/planner/system_v1.txt` defines declarative-only output and prohibits target access, code, selectors, and secret disclosure. |
| Validation boundary | Provider output is parsed into strict Pydantic models with no extra properties, then server- and request-owned source, limits, options, and outputs are checked. |
| Persistence boundary | Only the validated canonical plan is stored in `extraction_plans`; raw provider output, prompts, credentials, and request text are not stored as an execution plan. |

The worker records structured lifecycle logs with job, correlation, operation, version, and safe error-code metadata. It intentionally does not log a task, prompt, raw provider response, or credential.

## Provider configuration

The default production adapter sends an OpenAI Chat Completions-compatible request to `PLANNER_API_ENDPOINT/chat/completions`. The request uses temperature zero and strict JSON-schema output. A provider must be explicitly configured. Empty credentials, an invalid endpoint, unsupported provider selection, or provider authentication/configuration failure produce `PLANNER_UNAVAILABLE`; the application never substitutes a fake plan.

| Environment variable | Meaning | Default |
| --- | --- | --- |
| `PLANNER_PROVIDER` | Provider adapter identifier; currently `openai_compatible` | `openai_compatible` |
| `PLANNER_MODEL` | Provider model identifier | `gpt-5-mini` |
| `PLANNER_API_ENDPOINT` | Base API endpoint, without the Chat Completions suffix | Empty; required for production use |
| `PLANNER_API_KEY` | Provider credential | Empty; required for production use |
| `PLANNER_TIMEOUT_SECONDS` | Per-request provider timeout | `30` |
| `PLANNER_MAX_RETRIES` | Retry budget for transient planner failures | `2` |
| `PLANNER_MAX_OUTPUT_TOKENS` | Provider completion cap | `2048` |

No credential belongs in `.env.example`, source code, tests, documentation examples, or logs.

## Canonical plan schema

The stored plan conforms to schema version `plan.v1` and plan version `1`. It captures a source URL, semantic objective, named field definitions and types, navigation intent, deduplication intent, validation intent, resource limits, requested outputs, assumptions, and ambiguities. Supported semantic field types are `string`, `integer`, `number`, `boolean`, `date`, `datetime`, `url`, `email`, `currency`, and `text`. Supported plan outputs are `excel`, `csv`, `json`, `pdf`, `docx`, `markdown`, and `txt`.

The plan has no selector, XPath, browser script, crawler command, executable code, or target-derived fact. When the request does not permit a reliable field definition, a plan may retain an empty field list only when it records an explicit bounded ambiguity.

## Validation, hashing, and audit metadata

Validation is deterministic. It rejects unknown properties, unsupported types/formats, duplicate names, executable or selector-like text, source mutation, mismatched page bounds, requested-option mutation, requested-output mutation, and values above server ceilings. The initial source URL remains immutable in the plan.

After validation, the plan is serialized with stable key ordering and compact JSON and hashed with SHA-256. The hash is independent of database IDs and timestamps. `ExtractionPlan` persists the canonical JSON plus `provider_name`, `model_name`, `schema_version`, `prompt_version`, `plan_hash`, `version`, status, and creation time. The job-status API exposes only safe plan metadata: version, status, schema version, model name, hash, and creation time.

## Resource controls and error handling

The server remains authoritative over `PLANNER_MAX_TASK_CHARS`, page and record limits, maximum fields, maximum outputs, timeout, and retry budget. The user-requested limits are also immutable within a plan; the model may not increase, decrease, or replace them.

| Error class | Retry behavior | Durable result |
| --- | --- | --- |
| Timeout, rate limit, or unavailable provider | Retries with bounded exponential backoff and jitter up to `PLANNER_MAX_RETRIES` | Job remains `PLANNING`; an ordered retry event is persisted. |
| Invalid JSON or schema output | No retry | Job transitions to `FAILED` with a safe planner error code. |
| Prompt-injection policy rejection or output-policy violation | No retry | Job transitions to `FAILED` with a safe planner error code. |
| Cancellation | No retry | Cancellation is rechecked before planning, after model completion, and before plan persistence. |

The worker releases the lease on failure. Lease recovery remains owned by the existing durable recovery process and does not create a direct in-memory scheduling path.

## Local development and verification

Copy `.env.example` to `.env`, configure a real provider only when an intentional local planner run is required, and apply migrations through revision `0003_planner_metadata`. The test suite uses the deterministic model directly, so test execution does not require an external provider credential or target-site access.

Focused Phase 4 tests cover canonical hashing; strict schema and policy rejection; source, output, option, and limit immutability; bounded ambiguity; prompt-injection rejection; provider timeout/rate-limit/invalid-output classification; model configuration safety; persistence/audit metadata; cancellation; idempotent handoff behavior; worker retry classification; safe API status metadata; and Phase 3 browser-boundary regressions.

## Known limitations

Phase 4 is a planning layer, not a general security proxy or a source-inspection engine. It does not establish future discovery policies, page classification, extraction semantics, result validation behavior, export generation, multi-plan revisions, provider failover, or cost accounting. Those capabilities require their own later-phase specifications and tests.

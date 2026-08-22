# Roadmap and Phase Boundaries

## Fixed sequence

The product is developed in the following order and later phases must consume the contracts established earlier:

| Phase | Scope | Phase 0 dependency |
|---|---|---|
| 0 | Architecture and technical foundation | This document set |
| 1 | Next.js frontend | API and progress contracts |
| 2 | FastAPI backend and background jobs | Data model, lifecycle, API contracts |
| 3 | Async Playwright engine | Browser policy and worker boundary |
| 4 | AI planner | Plan schema, validation, and orchestration boundary |
| 5 | Page and link discovery | Browser snapshots and discovery contract |
| 6 | Data extraction | Plan, page evidence, and record contract |
| 7 | Validation | Candidate record and validation contract |
| 8 | Excel, CSV, and JSON export | Validated dataset and storage contract |
| 9 | Progress and results | Events, SSE, results, and file contracts |
| 10 | PDF, DOCX, Markdown, and TXT export | Export adapter boundary |
| 11 | Security and testing hardening | All component boundaries and threat model |
| 12 | Deployment and operations | Container, storage, queue, and observability design |

## Phase 0 deliverables

Phase 0 delivers a coherent monorepo layout, architecture overview, system design, data model, API contracts, job lifecycle, browser policy, security boundaries, storage abstraction, agent boundaries, and architecture decision record. It may include configuration and documentation scaffolding, but it does not implement future engines.

## Explicit non-goals

Phase 0 does not build a complete frontend, FastAPI endpoints, database migrations, Redis workers, Playwright automation, planner prompts, discovery algorithms, extraction parsers, validation rules, exporters, real-time UI, production deployment, or complete security controls. Minimal type or schema scaffolding is permitted only if it validates a contract without implementing product behavior.

## Exit criteria

Phase 0 is complete when the documentation is internally consistent, the repository layout is understandable, contracts describe inputs and outputs, failure and cancellation semantics are explicit, security boundaries address arbitrary URLs and untrusted content, storage is provider-independent, and no future-phase implementation has leaked into the foundation.

## Handoff rules

Each phase begins by reviewing the preceding contracts and adding tests for its own behavior. A later implementation may refine a contract only through a documented decision and compatibility review. Roadmap order must not be bypassed by adding a giant cross-phase implementation.

Phase 1 is the recommended next phase: build the Next.js client against the API and progress contracts, without implementing backend execution in the frontend.

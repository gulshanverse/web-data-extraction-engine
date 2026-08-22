# Agent and Engine Boundaries

## Principle

The platform is a coordinated set of bounded components, not one giant AI agent. The natural-language request is interpreted once into a machine-readable extraction plan. Downstream components execute within that plan and within independently enforced policy and resource limits.

## Planner Agent

**Input:** source URL, natural-language task, optional requested fields and constraints, crawl options, output formats, and the project policy summary.

**Output:** a schema-valid, versioned extraction plan containing target description, fields and types, page-selection intent, pagination behavior, link-following intent, deduplication rule, validation requirements, and requested formats. The plan records a model/provider identifier and schema version but not unrestricted prompt content or secrets.

The planner may suggest intent; it may not grant new domains, increase system safety limits, choose arbitrary tools, run code, access credentials, or bypass access controls. A deterministic validator rejects unsupported actions, missing required fields, excessive budgets, and inconsistent output requirements.

## Browser Agent

The Browser Agent owns browser interaction: navigation, waiting, clicking, scrolling, filling, selecting, opening permitted links, DOM inspection, and page-state capture. It consumes a validated action vocabulary and a browser policy. It emits page metadata, snapshots, and evidence.

It does not decide what the user wants, invent extraction fields, authorize domains, or write generated exports. Each action is checked for domain, redirect, resource, time, cancellation, and browser-context constraints.

## Discovery Agent

Discovery identifies where relevant data exists and proposes bounded page candidates such as category pages, pagination links, and product detail pages. It consumes captured page state and the extraction plan. It returns candidates with evidence, depth, canonical URL, and a reason code.

Discovery cannot expand beyond policy budgets or silently replace the user’s target. A candidate is not a permission grant; the browser policy is evaluated again before navigation.

## Extraction Engine

The Extraction Engine converts permitted page content into candidate structured records. It applies deterministic parsing, schema mapping, normalization, and provenance capture. Website-specific rules belong to a plan or adapter boundary and are not hardcoded into shared core logic.

The engine does not browse, decide whether a page is relevant, validate all business requirements, or serialize output files. It may produce partial candidates and confidence metadata for the Validation Engine.

## Validation Engine

Validation checks required fields, types, missing values, malformed values, duplicate records, invalid URLs, truncation, consistency, and extraction confidence. It returns structured findings, statuses, and safe diagnostics. Validation may mark records as passed, passed with warnings, or failed; it does not silently rewrite source evidence.

## Export Engine

The Export Engine receives validated records and a format request. It serializes data into Excel, CSV, JSON, and later PDF, DOCX, Markdown, or TXT through independent format adapters. It does not browse, extract, decide record validity, or change the active extraction plan.

## Orchestrator

The orchestrator owns job state, command scheduling, retry classification, cancellation, checkpoints, idempotency, and progress events. It invokes components through typed ports and persists outcomes. It does not contain site-specific extraction logic or model reasoning.

## Shared contracts

| Boundary | Contract |
|---|---|
| Planner → Orchestrator | Versioned `ExtractionPlan` with validated budgets and target schema |
| Orchestrator → Browser | `BrowserTask` containing job, page candidate, action plan, and immutable policy |
| Browser → Discovery | `PageSnapshot` and `PageEvidence` with canonical URL, hash, depth, and capture metadata |
| Discovery → Browser | Bounded `PageCandidate` list with evidence and requested traversal reason |
| Extraction → Validation | `CandidateRecord` with schema version, source page, plan version, field values, and provenance |
| Validation → Export | `ValidatedDataset` with validation summary, ordering, and schema version |
| Components → Orchestrator | Typed outcome, stable error code, counts, checkpoint, and emitted domain events |
| Components → Storage | `ArtifactStore` port, never provider-specific paths or SDK calls |

## AI reliability controls

Model output is treated as untrusted data. JSON/schema validation, allowed-enum checks, policy validation, maximum token/input constraints, and repair limits are applied before a plan is activated. A model cannot call the browser directly; it can only produce plan data consumed by deterministic orchestration.

Prompt injection defenses include separating page content from system instructions, treating all external text as data, constraining tools and arguments, and refusing instructions that request secrets, policy changes, arbitrary code, or access-control bypass. Model failures are explicit `PLAN_INVALID` or `INTERNAL_ERROR` outcomes, not implicit permission expansions.

## Phase 0 non-implementation

This document defines responsibilities and interfaces only. Planner prompts, browser workers, discovery logic, extraction parsers, validation rules, exporters, and frontend flows belong to later roadmap phases.

# ADR-002: Persist browser artifacts separately from generated exports

- **Status:** Accepted
- **Date:** 2026-08-22
- **Decision owners:** Project maintainers

## Context

Phase 3 needs durable references for screenshots and controlled downloads. The existing `generated_files` entity belongs to `export_jobs`, while the browser phase runs before discovery, extraction, validation, and export. Reusing export metadata would incorrectly imply an export existed and would blur ownership boundaries.

## Decision

Add `browser_artifacts`, owned by an `ExtractionJob` and optionally associated with a `Page`. It records only an opaque storage key, artifact kind, media type, byte size, checksum, expiry, and timestamps. Raw artifact bytes remain behind the existing storage abstraction. `pages` gains only safe navigation metadata needed to audit browser capture.

## Consequences

Browser evidence is queryable and authorization-aware without coupling it to exporter lifecycle. Future discovery and extraction phases can consume page/artifact references through typed contracts. Retention and signed-download behavior remain storage and authorization concerns; this decision does not expose browser artifacts through the public files endpoint.

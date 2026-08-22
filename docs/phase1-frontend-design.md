# Phase 1 Frontend Design

## Direction

Phase 1 uses the **Instrument Panel** design direction: an asymmetric technical workspace that makes the extraction workflow—not dashboard decoration—the primary composition. The visual language combines contemporary industrial design with Swiss information-system principles.

## Design system

| Element | Decision |
|---|---|
| Typography | Manrope for interface hierarchy; IBM Plex Mono for commands, metadata, and operational state |
| Working surface | Porcelain `#F7F6F2` with graphite `#1D2020` text and fine calibration rules |
| Signal color | Signal Orange `#E65722`, reserved for action, selection, live execution, and focused inputs |
| Geometry | Square-to-low-radius controls, hairline boundaries, and no decorative glass or gradients |
| Layout | Desktop operations bench with context rail, command sheet, and live state column; task order is preserved on mobile |
| Motion | Purposeful 140–220ms state transitions; no decorative motion; reduced motion is respected |

## Phase 1 behavior

The frontend provides a functional client-side workspace with source and intent inputs, bounded-crawl controls, accessible selectable format tiles, expandable advanced settings, and a mock job lifecycle. The mock lifecycle mirrors the Phase 0 event vocabulary so Phase 9 can replace it with SSE-backed events without redesigning the interface.

No backend routes, authentication, browser automation, planner, discovery, extraction, validation, or exporter implementation is included in this phase.

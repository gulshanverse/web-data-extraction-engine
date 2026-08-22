# Phase 1 Frontend Design

## Direction

Phase 1 uses the **Data Loom** direction: a composed, editorial data workbench rather than a dashboard template. A continuous extraction canvas moves from source to specification to structured output, while a live run thread makes the operation inspectable. The previous Instrument Panel direction is superseded.

## Semantic design system

| Element | Light mode | Dark mode | Intent |
|---|---|---|---|
| Background | Pale mineral | Layered peat | Calm application ground, never pure white or black |
| Primary surface | Warm paper | Charcoal slate | Main authoring workspace |
| Secondary surface | Mist green | Deep slate | Grouped controls, preview, and ledger support |
| Text | Ink | Soft limestone | High-contrast hierarchy |
| Accent | Verdigris Teal `#0F766E` | Softened teal | Action, selection, progress, and active state only |
| Semantic states | Sage success, amber warning, clay error, blue-gray information | Tonally adjusted counterparts | Communicate state without color-only dependence |

DM Sans provides display and interface typography; IBM Plex Mono provides URLs, counts, statuses, timestamps, and schema-adjacent metadata. Geometry follows meaning: soft-radius work surfaces, pill statuses, circular timeline nodes, compact segmented controls, and rounded input fields. Borders separate sections and inputs; they do not box every element.

## Phase 1 behavior

The frontend implements client-side validation, light/dark theme switching, a mock event service, source and extraction-brief authoring, compact crawl controls, selectable output formats, operation states, an output ledger, a result table preview, and a runs/history composition. Mock events map to the Phase 0 lifecycle and can be replaced by Phase 2 API calls and Phase 9 SSE without restructuring the UI.

No backend routes, authentication, browser automation, planner, discovery, extraction, validation engine, exporter, queue, database, or realtime transport is included in this phase.

## Visual self-critique applied

| Improvement | Applied change |
|---|---|
| Make the product identity ownable | Replaced the prior generic operational lockup with the `data/loom` wordmark and woven source mark. |
| Reduce dashboard-card grammar | Consolidated authoring into one curved extraction canvas with internal dividers instead of a stack of unrelated panels. |
| Make the workflow visible at a glance | Added the structural loom route through source, intent, configuration, formats, command, and operation state. |
| Strengthen idle-operation evidence | Reworked the right column into a preflight ledger showing source seal, schema, and output-package checkpoints before a run exists. |
| Improve state clarity and data-product credibility | Added typed mock lifecycle stages, light/dark semantic tokens, inline validation, a responsive results ledger, a sticky-header data table, and a no-fake-history ledger. |

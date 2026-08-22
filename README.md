# Web Data Extraction Engine

A modular web data extraction engine for discovering, extracting, validating, transforming, and exporting structured data from accessible websites.

## Purpose

The long-term product will accept a website URL, a natural-language extraction request, optional requirements, crawl controls, and requested output formats. It will turn that intent into a bounded asynchronous workflow for discovery, browser-assisted capture, deterministic extraction, validation, and export.

The platform is designed for publicly accessible content that the user is permitted to access. It is not a chatbot or a simple scraper, and it will not bypass CAPTCHA, authentication, authorization, paywalls, access controls, or other security mechanisms.

## Technology direction

The planned direction uses a Next.js and TypeScript web client, a Python/FastAPI API, asynchronous Playwright browser workers, PostgreSQL for durable state, Redis for background-job transport, and an S3-compatible storage abstraction with local filesystem support during development. Data-processing libraries such as Pandas, BeautifulSoup4, lxml, and OpenPyXL will be introduced when their corresponding capabilities are implemented.

## Project status

**Phase 0 — Architecture** is complete. The repository currently establishes the system design and contracts; functional frontend, backend, browser, AI planner, discovery, extraction, validation, export, and deployment components remain assigned to later phases.

See the [Phase 0 architecture documentation](docs/architecture.md) for the system overview. Related contracts and decisions are documented in:

- [System design](docs/system-design.md)
- [Data model](docs/data-model.md)
- [API contracts](docs/api-contracts.md)
- [Job lifecycle](docs/job-lifecycle.md)
- [Browser policy](docs/browser-policy.md)
- [Security boundaries](docs/security-boundaries.md)
- [Storage architecture](docs/storage-and-operations.md)
- [Agent boundaries](docs/agent-boundaries.md)
- [Roadmap and phase boundaries](docs/phase-boundaries.md)
- [ADR-001: Modular asynchronous architecture](docs/decisions/ADR-001-architecture.md)

Development will continue incrementally. The recommended next phase is **Phase 1 — Frontend**; it must not bypass the documented contracts or start future-phase implementation early.

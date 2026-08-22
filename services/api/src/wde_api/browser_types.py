"""Typed, Playwright-independent browser contracts for Phase 3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from wde_api.storage import ArtifactRef


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str
    message: str


@dataclass(frozen=True)
class BrowserOperationRequest:
    job_id: str
    project_id: str
    correlation_id: str
    operation_key: str
    url: str
    allowed_domain: str
    capture_screenshot: bool = True
    full_page_screenshot: bool = False


@dataclass(frozen=True)
class NavigationMetadata:
    requested_url: str
    final_url: str
    status: int | None
    content_type: str | None
    title: str | None
    viewport: dict[str, int]
    redirect_count: int
    navigation_time_ms: int


@dataclass(frozen=True)
class BrowserArtifactResult:
    kind: str
    artifact: ArtifactRef


@dataclass(frozen=True)
class BrowserOperationResult:
    navigation: NavigationMetadata
    artifacts: tuple[BrowserArtifactResult, ...] = ()
    events: tuple[dict[str, object], ...] = ()


class BrowserEngine(Protocol):
    async def capture(self, request: BrowserOperationRequest) -> BrowserOperationResult: ...


class BrowserPolicy(Protocol):
    async def allow_navigation(self, url: str, from_url: str | None = None) -> PolicyDecision: ...

    async def allow_request(
        self, url: str, resource_type: str, from_url: str | None = None
    ) -> PolicyDecision: ...

    def allow_page_count(self, current: int) -> PolicyDecision: ...

    def allow_redirect_count(self, current: int) -> PolicyDecision: ...

    async def should_cancel(self, job_id: str) -> bool: ...

"""Typed, declarative Phase 5 discovery contracts with no record-extraction fields."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InventoryStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    VISITED = "VISITED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class DiscoveryMethod(StrEnum):
    SOURCE = "source"
    LINK = "link"
    PAGINATION = "pagination"
    RELEVANT_LINK = "relevant_link"
    SITEMAP = "sitemap"


class ScopePolicy(StrEnum):
    SAME_ORIGIN = "SAME_ORIGIN"
    SAME_SITE = "SAME_SITE"
    EXPLICIT_ALLOWED_DOMAINS = "EXPLICIT_ALLOWED_DOMAINS"


@dataclass(frozen=True)
class NavigationSignal:
    href: str
    text: str = ""
    rel: str = ""
    aria_label: str = ""


@dataclass(frozen=True)
class DiscoveryCandidate:
    url: str
    canonical_url: str
    discovered_via: DiscoveryMethod
    depth: int
    parent_canonical_url: str | None
    policy_decision: str
    relevance_score: float | None = None
    relevance_reason: str | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    job_id: str
    source_url: str
    discovered_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    inventory_status: str
    metadata: dict[str, object]

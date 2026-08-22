"""Phase 5 navigation-candidate analysis; it is deliberately separate from browser I/O and persistence."""

from __future__ import annotations

import re
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from urllib.parse import urlsplit

from wde_api.config import Settings
from wde_api.discovery_policy import DiscoveryScope, canonicalize_url, is_pagination_signal
from wde_api.discovery_types import DiscoveryCandidate, DiscoveryMethod, NavigationSignal, ScopePolicy
from wde_api.planner_types import CanonicalPlan


@dataclass(frozen=True)
class CandidateDecision:
    candidates: tuple[DiscoveryCandidate, ...]
    rejected: tuple[DiscoveryCandidate, ...]
    duplicate_count: int


class DiscoveryService:
    """Produces explainable URL candidates only; it never yields fields, records, selectors, or business data."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def scope_for(self, plan: CanonicalPlan) -> DiscoveryScope:
        try:
            policy = ScopePolicy(self.settings.discovery_scope_policy)
        except ValueError:
            policy = ScopePolicy.SAME_ORIGIN
        return DiscoveryScope(source_url=plan.source.url, policy=policy)

    def from_signals(
        self,
        *,
        plan: CanonicalPlan,
        parent_url: str,
        parent_canonical_url: str,
        parent_depth: int,
        signals: tuple[NavigationSignal, ...],
        seen_urls: set[str],
    ) -> CandidateDecision:
        scope = self.scope_for(plan)
        candidates: list[DiscoveryCandidate] = []
        rejected: list[DiscoveryCandidate] = []
        duplicate_count = 0
        if parent_depth >= min(plan.limits.max_pages, self.settings.discovery_max_depth):
            return CandidateDecision((), (), 0)
        max_depth = self.settings.discovery_max_depth
        if parent_depth + 1 > max_depth:
            return CandidateDecision((), (), 0)
        for signal in signals[: self.settings.discovery_max_links_per_page]:
            canonical = canonicalize_url(signal.href, base_url=parent_url)
            if canonical is None:
                continue
            allowed, decision = scope.allows(canonical)
            method, score, reason = self._classify_signal(plan, signal, canonical)
            candidate = DiscoveryCandidate(
                url=canonical,
                canonical_url=canonical,
                discovered_via=method,
                depth=parent_depth + 1,
                parent_canonical_url=parent_canonical_url,
                policy_decision=decision,
                relevance_score=score,
                relevance_reason=reason,
            )
            if canonical in seen_urls or any(item.canonical_url == canonical for item in candidates):
                duplicate_count += 1
                continue
            if not allowed:
                rejected.append(candidate)
                continue
            if method == DiscoveryMethod.PAGINATION and plan.navigation.follow_pagination:
                candidates.append(candidate)
                continue
            if method == DiscoveryMethod.RELEVANT_LINK and plan.navigation.follow_relevant_links:
                candidates.append(candidate)
        return CandidateDecision(tuple(candidates), tuple(rejected), duplicate_count)

    def sitemap_candidates(
        self,
        *,
        plan: CanonicalPlan,
        sitemap_text: str,
        parent_canonical_url: str,
        parent_depth: int,
        seen_urls: set[str],
    ) -> CandidateDecision:
        """Safely parse bounded XML sitemap locations into URLs; it does not fetch or persist XML."""
        if len(sitemap_text.encode("utf-8")) > self.settings.discovery_sitemap_max_bytes:
            return CandidateDecision((), (), 0)
        try:
            root = element_tree.fromstring(sitemap_text)
        except element_tree.ParseError:
            return CandidateDecision((), (), 0)
        locations = [node.text.strip() for node in root.iter() if node.tag.endswith("loc") and node.text]
        scope = self.scope_for(plan)
        candidates: list[DiscoveryCandidate] = []
        rejected: list[DiscoveryCandidate] = []
        duplicate_count = 0
        for value in locations[: self.settings.discovery_sitemap_max_urls]:
            canonical = canonicalize_url(value)
            if canonical is None:
                continue
            allowed, decision = scope.allows(canonical)
            candidate = DiscoveryCandidate(
                url=canonical,
                canonical_url=canonical,
                discovered_via=DiscoveryMethod.SITEMAP,
                depth=parent_depth + 1,
                parent_canonical_url=parent_canonical_url,
                policy_decision=decision,
                relevance_reason="sitemap location",
            )
            if canonical in seen_urls or any(item.canonical_url == canonical for item in candidates):
                duplicate_count += 1
            elif allowed and parent_depth + 1 <= self.settings.discovery_max_depth:
                candidates.append(candidate)
            elif not allowed:
                rejected.append(candidate)
        return CandidateDecision(tuple(candidates), tuple(rejected), duplicate_count)

    def default_sitemap_url(self, source_url: str) -> str | None:
        parsed = urlsplit(source_url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return canonicalize_url(f"{parsed.scheme}://{parsed.netloc}/sitemap.xml")

    @staticmethod
    def _classify_signal(
        plan: CanonicalPlan, signal: NavigationSignal, canonical: str
    ) -> tuple[DiscoveryMethod, float | None, str | None]:
        if is_pagination_signal(signal.text, signal.rel, canonical):
            return DiscoveryMethod.PAGINATION, None, "pagination signal"
        corpus = " ".join([signal.text, signal.aria_label, canonical, plan.intent.summary]).lower()
        tokens = {item for item in re.findall(r"[a-z0-9]{3,}", plan.intent.summary.lower())}
        matched = sorted(token for token in tokens if token in corpus)
        score = min(1.0, 0.25 + 0.15 * len(matched)) if matched else 0.1
        reason = "keyword overlap" if matched else "same-scope navigation link"
        return DiscoveryMethod.RELEVANT_LINK, score, reason

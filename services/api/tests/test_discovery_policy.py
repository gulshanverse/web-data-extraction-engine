from __future__ import annotations

from planner_fixtures import valid_plan
from wde_api.config import Settings
from wde_api.discovery_policy import DiscoveryScope, canonicalize_url
from wde_api.discovery_service import DiscoveryService
from wde_api.discovery_types import NavigationSignal, ScopePolicy
from wde_api.planner_types import CanonicalPlan


def plan(*, follow_relevant_links: bool = True) -> CanonicalPlan:
    raw = valid_plan()
    raw["navigation"]["follow_relevant_links"] = follow_relevant_links
    return CanonicalPlan.model_validate(raw)


def test_canonicalization_resolves_links_and_preserves_meaningful_queries() -> None:
    assert canonicalize_url("../item/./1#part", base_url="https://EXAMPLE.com/products/page/") == (
        "https://example.com/products/item/1"
    )
    assert (
        canonicalize_url("https://example.com:443/products?page=2#fragment")
        == "https://example.com/products?page=2"
    )
    assert canonicalize_url("javascript:alert(1)") is None
    assert canonicalize_url("mailto:help@example.com") is None


def test_scope_is_conservative_and_does_not_assume_subdomains_are_in_scope() -> None:
    scope = DiscoveryScope("https://example.com/products", ScopePolicy.SAME_ORIGIN)
    assert scope.allows("https://example.com/products?page=2") == (True, "ALLOWED")
    assert scope.allows("https://shop.example.com/products") == (False, "SCOPE_DENIED")
    assert scope.allows("https://other.example/products") == (False, "SCOPE_DENIED")


def test_signal_discovery_is_bounded_and_classifies_pagination_relevance_and_scope() -> None:
    service = DiscoveryService(Settings(discovery_max_depth=2, discovery_max_links_per_page=4))
    result = service.from_signals(
        plan=plan(),
        parent_url="https://example.com/products",
        parent_canonical_url="https://example.com/products",
        parent_depth=0,
        signals=(
            NavigationSignal("?page=2", "Next", "next"),
            NavigationSignal("/products/item/1", "Product 1"),
            NavigationSignal("https://outside.example/news", "News"),
            NavigationSignal("/products/item/1#details", "Product duplicate"),
        ),
        seen_urls={"https://example.com/products"},
    )
    assert {candidate.discovered_via.value for candidate in result.candidates} == {
        "pagination",
        "relevant_link",
    }
    assert result.rejected[0].policy_decision == "SCOPE_DENIED"
    assert result.duplicate_count == 1


def test_sitemap_parser_is_bounded_deduplicated_and_scope_checked() -> None:
    service = DiscoveryService(Settings(discovery_sitemap_max_urls=2, discovery_max_depth=2))
    result = service.sitemap_candidates(
        plan=plan(),
        sitemap_text="""<urlset><url><loc>https://example.com/a</loc></url><url><loc>https://example.com/a#x</loc></url><url><loc>https://outside.example/b</loc></url></urlset>""",
        parent_canonical_url="https://example.com/sitemap.xml",
        parent_depth=0,
        seen_urls=set(),
    )
    assert [candidate.canonical_url for candidate in result.candidates] == ["https://example.com/a"]
    assert result.duplicate_count == 1

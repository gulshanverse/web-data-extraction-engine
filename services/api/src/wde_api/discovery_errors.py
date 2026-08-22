"""Stable Phase 5 discovery errors; none represent extraction outcomes."""

from __future__ import annotations


class DiscoveryError(Exception):
    code = "DISCOVERY_FAILED"
    retryable = False

    def __init__(self, message: str = "Discovery could not complete safely.") -> None:
        super().__init__(message)
        self.message = message


class DiscoveryTimeout(DiscoveryError):
    code = "DISCOVERY_TIMEOUT"
    retryable = True


class DiscoveryNavigationFailed(DiscoveryError):
    code = "DISCOVERY_NAVIGATION_FAILED"
    retryable = True


class DiscoveryBrowserFailed(DiscoveryError):
    code = "DISCOVERY_BROWSER_FAILED"
    retryable = True


class DiscoveryPolicyBlocked(DiscoveryError):
    code = "DISCOVERY_POLICY_BLOCKED"


class DiscoveryScopeDenied(DiscoveryError):
    code = "DISCOVERY_SCOPE_DENIED"


class DiscoveryLimitReached(DiscoveryError):
    code = "DISCOVERY_LIMIT_REACHED"


class DiscoveryCancelled(DiscoveryError):
    code = "DISCOVERY_CANCELLED"


class DiscoverySitemapTooLarge(DiscoveryError):
    code = "DISCOVERY_SITEMAP_TOO_LARGE"

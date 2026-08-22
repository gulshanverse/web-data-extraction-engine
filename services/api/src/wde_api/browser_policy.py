"""Fail-closed, DNS-aware navigation policy for the Phase 3 browser runtime."""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from wde_api.browser_types import BrowserPolicy, PolicyDecision

Resolver = Callable[[str], Awaitable[list[str]]]
CancellationProbe = Callable[[str], Awaitable[bool]]


async def resolve_public(host: str) -> list[str]:
    answers = await asyncio.get_running_loop().getaddrinfo(host, None, type=0)
    return sorted({item[4][0] for item in answers})


def deny(code: str, message: str) -> PolicyDecision:
    return PolicyDecision(False, code, message)


def allow() -> PolicyDecision:
    return PolicyDecision(True, "ALLOWED", "Navigation permitted.")


def is_unsafe_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


@dataclass
class DefaultBrowserPolicy(BrowserPolicy):
    allowed_domain: str
    max_pages: int
    max_redirects: int
    resolver: Resolver = resolve_public
    cancellation_probe: CancellationProbe | None = None
    allow_subdomains: bool = True

    def _canonical(self, url: str) -> tuple[str, str] | None:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username or parsed.password or parsed.fragment:
            return None
        host = parsed.hostname.lower().rstrip(".")
        try:
            port = f":{parsed.port}" if parsed.port else ""
        except ValueError:
            return None
        if parsed.port not in {None, 80, 443}:
            return None
        return host, urlunsplit(
            (parsed.scheme.lower(), f"{host}{port}", parsed.path or "/", parsed.query, "")
        )

    def _domain_allowed(self, host: str) -> bool:
        root = self.allowed_domain.lower().rstrip(".")
        return host == root or (self.allow_subdomains and host.endswith(f".{root}"))

    async def allow_navigation(self, url: str, from_url: str | None = None) -> PolicyDecision:
        canonical = self._canonical(url)
        if canonical is None:
            return deny("URL_POLICY_BLOCKED", "The requested URL is not a supported public web address.")
        host, _ = canonical
        if not self._domain_allowed(host):
            code = "REDIRECT_BLOCKED" if from_url else "DOMAIN_NOT_ALLOWED"
            return deny(code, "The requested destination is not permitted by the browser policy.")
        try:
            answers = await self.resolver(host)
        except OSError:
            return deny("URL_POLICY_BLOCKED", "The requested destination could not be resolved safely.")
        if not answers or any(is_unsafe_address(answer) for answer in answers):
            return deny(
                "URL_POLICY_BLOCKED", "The requested destination is not permitted by the browser policy."
            )
        return allow()

    async def allow_request(
        self, url: str, resource_type: str, from_url: str | None = None
    ) -> PolicyDecision:
        if resource_type in {"websocket", "other"}:
            return deny("RESOURCE_TYPE_BLOCKED", "The requested browser resource type is not permitted.")
        return await self.allow_navigation(url, from_url)

    def allow_page_count(self, current: int) -> PolicyDecision:
        return (
            allow()
            if current < self.max_pages
            else deny("RESOURCE_LIMIT_EXCEEDED", "The browser page limit was reached.")
        )

    def allow_redirect_count(self, current: int) -> PolicyDecision:
        return (
            allow()
            if current <= self.max_redirects
            else deny("RESOURCE_LIMIT_EXCEEDED", "The browser redirect limit was reached.")
        )

    async def should_cancel(self, job_id: str) -> bool:
        return await self.cancellation_probe(job_id) if self.cancellation_probe else False

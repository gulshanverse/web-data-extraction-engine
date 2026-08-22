"""Deterministic Phase 5 URL normalization and scope decisions, separate from browser navigation policy."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from wde_api.discovery_types import ScopePolicy

_UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
_SUPPORTED_SCHEMES = {"http", "https"}


def _normalize_percent(value: str, *, safe: str) -> str:
    return quote(unquote(value), safe=safe + _UNRESERVED)


def canonicalize_url(url: str, *, base_url: str | None = None) -> str | None:
    """Resolve a navigation link and normalize scheme, host, port, path, encoding, and fragments."""
    resolved = urljoin(base_url, url) if base_url else url
    parsed = urlsplit(resolved)
    scheme = parsed.scheme.lower()
    if scheme not in _SUPPORTED_SCHEMES or not parsed.hostname or parsed.username or parsed.password:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    host = parsed.hostname.lower().rstrip(".")
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    raw_path = parsed.path or "/"
    normalized_path = posixpath.normpath(raw_path)
    if raw_path.endswith("/") and not normalized_path.endswith("/"):
        normalized_path += "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    normalized_path = _normalize_percent(normalized_path, safe="/%:@")
    query = _normalize_percent(parsed.query, safe="=&;/?:@+$,[]")
    return urlunsplit((scheme, netloc, normalized_path, query, ""))


def origin(url: str) -> tuple[str, str, int] | None:
    parsed = urlsplit(url)
    if parsed.scheme not in _SUPPORTED_SCHEMES or not parsed.hostname:
        return None
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    return parsed.scheme.lower(), parsed.hostname.lower().rstrip("."), port


def registrable_site(host: str) -> str:
    """Conservative same-site approximation; public-suffix awareness is intentionally not implied."""
    labels = host.lower().rstrip(".").split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host.lower().rstrip(".")


@dataclass(frozen=True)
class DiscoveryScope:
    source_url: str
    policy: ScopePolicy = ScopePolicy.SAME_ORIGIN
    allowed_domains: frozenset[str] = frozenset()

    def allows(self, url: str) -> tuple[bool, str]:
        source_origin = origin(self.source_url)
        candidate_origin = origin(url)
        if source_origin is None or candidate_origin is None:
            return False, "UNSUPPORTED_URL"
        if self.policy == ScopePolicy.SAME_ORIGIN:
            return (
                candidate_origin == source_origin,
                "ALLOWED" if candidate_origin == source_origin else "SCOPE_DENIED",
            )
        if self.policy == ScopePolicy.SAME_SITE:
            allowed = candidate_origin[0] == source_origin[0] and registrable_site(
                candidate_origin[1]
            ) == registrable_site(source_origin[1])
            return allowed, "ALLOWED" if allowed else "SCOPE_DENIED"
        domains = {item.lower().rstrip(".") for item in self.allowed_domains}
        allowed = candidate_origin[1] in domains
        return allowed, "ALLOWED" if allowed else "SCOPE_DENIED"


def is_pagination_signal(signal_text: str, rel: str, href: str) -> bool:
    value = " ".join([signal_text, rel]).lower()
    if "next" in value or re.search(r"\bpage\s*\d+\b", value):
        return True
    return "page=" in href.lower() and ("next" in value or rel.lower() == "next")

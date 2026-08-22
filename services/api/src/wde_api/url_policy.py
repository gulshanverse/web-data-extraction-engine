"""Initial API URL policy. It validates input without performing DNS, redirects, browser navigation, or any bypass behavior."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from wde_api.domain import DomainError


class InvalidUrl(DomainError):
    code = "INVALID_URL"
    status_code = 400


class DomainNotAllowed(DomainError):
    code = "DOMAIN_NOT_ALLOWED"
    status_code = 403


@dataclass(frozen=True)
class CanonicalUrl:
    canonical_url: str
    domain: str


def validate_initial_url(raw: str) -> CanonicalUrl:
    if len(raw) > 2048:
        raise InvalidUrl("The source URL exceeds the maximum length.")
    try:
        parsed = urlsplit(raw.strip())
    except ValueError as exc:
        raise InvalidUrl("The source URL is malformed.") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise InvalidUrl("Only http and https source URLs are supported.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise InvalidUrl("The source URL must contain a public hostname and no embedded credentials.")
    if parsed.fragment:
        raise InvalidUrl("The source URL must not contain a fragment.")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise DomainNotAllowed("The requested domain is not permitted.")
    try:
        address = ipaddress.ip_address(host)
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise DomainNotAllowed("The requested domain is not permitted.")
    except ValueError:
        if "." not in host or any(label == "" for label in host.split(".")):
            raise InvalidUrl("The source URL must contain a valid public hostname.") from None
    try:
        if parsed.port not in {None, 80, 443}:
            raise InvalidUrl("The source URL uses a port that is not permitted.")
    except ValueError as exc:
        raise InvalidUrl("The source URL is malformed.") from exc
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    path = parsed.path or "/"
    return CanonicalUrl(urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, "")), host)

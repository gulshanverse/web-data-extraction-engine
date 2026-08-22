import pytest
from wde_api.browser_policy import DefaultBrowserPolicy, is_unsafe_address


async def public_resolver(_: str) -> list[str]:
    return ["93.184.216.34"]


async def private_resolver(_: str) -> list[str]:
    return ["10.0.0.12"]


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "::1", "10.0.0.1", "192.168.1.1", "169.254.1.1", "fc00::1", "224.0.0.1"],
)
def test_marks_internal_and_reserved_addresses_unsafe(address: str) -> None:
    assert is_unsafe_address(address)


@pytest.mark.asyncio
async def test_accepts_only_permitted_http_domains_with_public_resolution() -> None:
    policy = DefaultBrowserPolicy("example.test", 1, 3, resolver=public_resolver)
    assert (await policy.allow_navigation("https://example.test/ok")).allowed
    assert (await policy.allow_navigation("https://sub.example.test/ok")).allowed
    denied = await policy.allow_navigation("https://other.test/ok")
    assert not denied.allowed and denied.code == "DOMAIN_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_rejects_unsupported_schemes_credentials_and_private_dns_answers() -> None:
    policy = DefaultBrowserPolicy("example.test", 1, 3, resolver=private_resolver)
    assert not (await policy.allow_navigation("file:///etc/passwd")).allowed
    assert not (await policy.allow_navigation("https://user:pass@example.test/secret")).allowed
    denied = await policy.allow_navigation("https://example.test/ok")
    assert not denied.allowed and denied.code == "URL_POLICY_BLOCKED"


def test_enforces_page_and_redirect_limits() -> None:
    policy = DefaultBrowserPolicy("example.test", 1, 2, resolver=public_resolver)
    assert policy.allow_page_count(0).allowed
    assert not policy.allow_page_count(1).allowed
    assert policy.allow_redirect_count(2).allowed
    assert not policy.allow_redirect_count(3).allowed

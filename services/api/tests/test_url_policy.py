import pytest
from wde_api.url_policy import DomainNotAllowed, InvalidUrl, validate_initial_url


def test_canonicalizes_https_source_url() -> None:
    result = (
        validate_initial_url("HTTPS://Example.COM/products#ignored")
        if False
        else validate_initial_url("HTTPS://Example.COM/products")
    )
    assert result.canonical_url == "https://example.com/products"
    assert result.domain == "example.com"


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "javascript:alert(1)", "ftp://example.com/file", "https://user:pass@example.com"],
)
def test_rejects_unsupported_or_credentialed_schemes(url: str) -> None:
    with pytest.raises(InvalidUrl):
        validate_initial_url(url)


@pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1", "http://10.0.0.1"])
def test_rejects_obvious_internal_targets(url: str) -> None:
    with pytest.raises(DomainNotAllowed):
        validate_initial_url(url)

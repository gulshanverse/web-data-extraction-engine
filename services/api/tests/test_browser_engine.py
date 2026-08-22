import asyncio
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright
from wde_api.browser_engine import PlaywrightBrowserEngine
from wde_api.browser_errors import (
    BrowserCancelled,
    BrowserPolicyBlocked,
    BrowserResourceLimit,
    DownloadTooLarge,
    NavigationTimeout,
)
from wde_api.browser_types import BrowserOperationRequest, PolicyDecision
from wde_api.config import Settings


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/start":
            self.send_response(302)
            self.send_header("Location", "/allowed")
            self.end_headers()
            return
        if self.path == "/to-blocked":
            self.send_response(302)
            self.send_header("Location", "/blocked")
            self.end_headers()
            return
        if self.path == "/slow":
            time.sleep(1.2)
        if self.path == "/download-small":
            payload = b"small controlled browser download"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=fixture.bin")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/download-large":
            payload = b"x" * 131_072
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=large.bin")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        title = "Allowed fixture" if self.path == "/allowed" else "Local fixture"
        body = f"<html><head><title>{title}</title></head><body><h1>{title}</h1><a href='/download-small'>Download</a></body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return


@pytest.fixture
def local_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


class FixturePolicy:
    def __init__(
        self, *, block_path: str | None = None, cancel_after: float | None = None, max_pages: int = 1
    ) -> None:
        self.block_path = block_path
        self.cancel_after = cancel_after
        self.max_pages = max_pages
        self.started = time.monotonic()

    async def allow_navigation(self, url: str, from_url: str | None = None) -> PolicyDecision:
        if self.block_path and self.block_path in url:
            return PolicyDecision(False, "REDIRECT_BLOCKED", "Fixture policy blocked this redirect.")
        return PolicyDecision(True, "ALLOWED", "Fixture URL allowed.")

    async def allow_request(
        self, url: str, resource_type: str, from_url: str | None = None
    ) -> PolicyDecision:
        return await self.allow_navigation(url, from_url)

    def allow_page_count(self, current: int) -> PolicyDecision:
        return (
            PolicyDecision(True, "ALLOWED", "Page capacity available.")
            if current < self.max_pages
            else PolicyDecision(False, "RESOURCE_LIMIT_EXCEEDED", "Fixture page limit reached.")
        )

    def allow_redirect_count(self, current: int) -> PolicyDecision:
        return (
            PolicyDecision(True, "ALLOWED", "Redirect capacity available.")
            if current <= 5
            else PolicyDecision(False, "RESOURCE_LIMIT_EXCEEDED", "Fixture redirect limit reached.")
        )

    async def should_cancel(self, job_id: str) -> bool:
        del job_id
        return self.cancel_after is not None and time.monotonic() - self.started >= self.cancel_after


def request(url: str, *, screenshot: bool = True) -> BrowserOperationRequest:
    return BrowserOperationRequest(
        "job-test", "project-test", "correlation-test", "operation-test", url, "127.0.0.1", screenshot
    )


def engine(tmp_path: Path, policy: FixturePolicy, **settings: object) -> PlaywrightBrowserEngine:
    values: dict[str, object] = {
        "artifact_root": tmp_path,
        "browser_headless": True,
        "browser_navigation_timeout_ms": 1_000,
        "browser_action_timeout_ms": 1_000,
        "browser_max_lifetime_seconds": 5,
        "browser_max_screenshot_bytes": 1_000_000,
        "browser_max_download_bytes": 1_000_000,
    }
    values.update(settings)
    config = Settings(**values)
    return PlaywrightBrowserEngine.from_settings(config, lambda _: policy)


@pytest.mark.asyncio
async def test_loads_local_page_captures_metadata_and_stores_viewport_screenshot(
    tmp_path: Path, local_server: str
) -> None:
    result = await engine(tmp_path, FixturePolicy()).capture(request(f"{local_server}/allowed"))
    assert result.navigation.final_url.endswith("/allowed")
    assert result.navigation.status == 200
    assert result.navigation.title == "Allowed fixture"
    assert result.navigation.content_type and result.navigation.content_type.startswith("text/html")
    assert result.artifacts[0].artifact.media_type == "image/png"
    assert (tmp_path / result.artifacts[0].artifact.key).exists()
    assert any(event["type"] == "browser_launched" for event in result.events)


@pytest.mark.asyncio
async def test_allows_local_redirect_and_records_final_url(tmp_path: Path, local_server: str) -> None:
    result = await engine(tmp_path, FixturePolicy()).capture(
        request(f"{local_server}/start", screenshot=False)
    )
    assert result.navigation.final_url.endswith("/allowed")
    assert result.navigation.redirect_count >= 1


@pytest.mark.asyncio
async def test_blocks_redirect_and_cleans_browser_resources(tmp_path: Path, local_server: str) -> None:
    with pytest.raises(BrowserPolicyBlocked) as error:
        await engine(tmp_path, FixturePolicy(block_path="/blocked")).capture(
            request(f"{local_server}/to-blocked", screenshot=False)
        )
    assert error.value.code == "REDIRECT_BLOCKED"
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.asyncio
async def test_navigation_timeout_is_structured_and_cleanup_is_atomic(
    tmp_path: Path, local_server: str
) -> None:
    with pytest.raises(NavigationTimeout):
        await engine(tmp_path, FixturePolicy(), browser_navigation_timeout_ms=1_000).capture(
            request(f"{local_server}/slow", screenshot=False)
        )
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.asyncio
async def test_cooperative_cancellation_stops_slow_navigation(tmp_path: Path, local_server: str) -> None:
    with pytest.raises(BrowserCancelled):
        await engine(tmp_path, FixturePolicy(cancel_after=0.2)).capture(
            request(f"{local_server}/slow", screenshot=False)
        )
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.asyncio
async def test_page_limit_rejects_before_launch(tmp_path: Path, local_server: str) -> None:
    with pytest.raises(BrowserResourceLimit):
        await engine(tmp_path, FixturePolicy(max_pages=0)).capture(request(f"{local_server}/allowed"))


@pytest.mark.asyncio
async def test_downloads_use_opaque_artifact_storage_and_size_limits(
    tmp_path: Path, local_server: str
) -> None:
    runtime = engine(tmp_path, FixturePolicy(), browser_max_download_bytes=65_536)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        async with page.expect_download() as captured:
            with pytest.raises(PlaywrightError, match="Download is starting"):
                await page.goto(f"{local_server}/download-small")
        artifact = await runtime._store_download(await captured.value)
        assert artifact.artifact.key and "/" not in artifact.artifact.key
        assert (tmp_path / artifact.artifact.key).exists()
        async with page.expect_download() as oversized:
            with pytest.raises(PlaywrightError, match="Download is starting"):
                await page.goto(f"{local_server}/download-large")
        with pytest.raises(DownloadTooLarge):
            await runtime._store_download(await oversized.value)
        await context.close()
        await browser.close()


@pytest.mark.asyncio
async def test_context_capacity_serializes_browser_operations(tmp_path: Path, local_server: str) -> None:
    runtime = engine(tmp_path, FixturePolicy(), browser_max_contexts=1, browser_navigation_timeout_ms=2_000)
    started = time.monotonic()
    await asyncio.gather(
        runtime.capture(request(f"{local_server}/slow", screenshot=False)),
        runtime.capture(request(f"{local_server}/slow", screenshot=False)),
    )
    assert time.monotonic() - started >= 2.0

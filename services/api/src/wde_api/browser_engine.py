"""Phase 3 isolated Chromium runtime. Only this module imports raw Playwright objects."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

import structlog
from playwright.async_api import Download, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from wde_api.browser_errors import (
    BrowserCancelled,
    BrowserCrashed,
    BrowserLaunchError,
    BrowserPolicyBlocked,
    BrowserResourceLimit,
    BrowserTimeout,
    DownloadTooLarge,
    NavigationFailed,
    NavigationTimeout,
    PageCrashed,
)
from wde_api.browser_types import (
    BrowserArtifactResult,
    BrowserEngine,
    BrowserOperationRequest,
    BrowserOperationResult,
    BrowserPolicy,
    NavigationMetadata,
    PolicyDecision,
)
from wde_api.config import Settings
from wde_api.storage import LocalArtifactStore

log = structlog.get_logger()


@dataclass
class BrowserCapacity:
    maximum: int
    _semaphore: asyncio.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self._semaphore = asyncio.Semaphore(self.maximum)

    async def acquire(self) -> None:
        await self._semaphore.acquire()

    def release(self) -> None:
        self._semaphore.release()


async def bytes_stream(payload: bytes) -> AsyncIterator[bytes]:
    yield payload


@dataclass
class PlaywrightBrowserEngine(BrowserEngine):
    settings: Settings
    policy_factory: Callable[[BrowserOperationRequest], BrowserPolicy]
    artifact_store: LocalArtifactStore
    capacity: BrowserCapacity

    @classmethod
    def from_settings(
        cls, settings: Settings, policy_factory: Callable[[BrowserOperationRequest], BrowserPolicy]
    ) -> PlaywrightBrowserEngine:
        return cls(
            settings=settings,
            policy_factory=policy_factory,
            artifact_store=LocalArtifactStore(
                settings.artifact_root, max_bytes=settings.browser_max_download_bytes
            ),
            capacity=BrowserCapacity(settings.browser_max_contexts),
        )

    async def capture(self, request: BrowserOperationRequest) -> BrowserOperationResult:
        policy: BrowserPolicy = self.policy_factory(request)
        decision = await policy.allow_navigation(request.url)
        self._require(decision)
        self._require(policy.allow_page_count(0))
        if await policy.should_cancel(request.job_id):
            raise BrowserCancelled("Browser work was cancelled before launch.")
        await self.capacity.acquire()
        started = time.monotonic()
        browser = context = page = None
        download_tasks: list[asyncio.Task[BrowserArtifactResult]] = []
        lifecycle_events: list[dict[str, object]] = []
        blocked: PolicyDecision | None = None
        navigation_urls: list[str] = []
        try:
            async with asyncio.timeout(self.settings.browser_max_lifetime_seconds):
                log.info("browser.launch.started", job_id=request.job_id, operation_key=request.operation_key)
                async with async_playwright() as playwright:
                    try:
                        browser = await asyncio.wait_for(
                            playwright.chromium.launch(headless=self.settings.browser_headless),
                            timeout=self.settings.browser_launch_timeout_ms / 1000,
                        )
                    except (PlaywrightError, TimeoutError) as error:
                        raise BrowserLaunchError("The browser could not start safely.") from error
                    lifecycle_events.append({"type": "browser_launched"})
                    log.info(
                        "browser.launch.completed", job_id=request.job_id, operation_key=request.operation_key
                    )
                    context = await asyncio.wait_for(
                        browser.new_context(
                            viewport={
                                "width": self.settings.browser_viewport_width,
                                "height": self.settings.browser_viewport_height,
                            },
                            locale=self.settings.browser_locale,
                            timezone_id=self.settings.browser_timezone_id,
                            user_agent=self.settings.browser_user_agent,
                            java_script_enabled=True,
                            accept_downloads=True,
                            permissions=[],
                        ),
                        timeout=self.settings.browser_action_timeout_ms / 1000,
                    )
                    lifecycle_events.append({"type": "context_created"})
                    page = await asyncio.wait_for(
                        context.new_page(), timeout=self.settings.browser_action_timeout_ms / 1000
                    )
                    page.set_default_timeout(self.settings.browser_action_timeout_ms)
                    lifecycle_events.append({"type": "page_created"})

                    async def close_unsolicited_page(opened_page: Page) -> None:
                        if opened_page is not page:
                            await opened_page.close()

                    context.on(
                        "page", lambda opened_page: asyncio.create_task(close_unsolicited_page(opened_page))
                    )

                    async def route_handler(route, routed_request) -> None:
                        nonlocal blocked
                        origin = routed_request.frame.url if routed_request.frame else None
                        request_decision = await policy.allow_request(
                            routed_request.url, routed_request.resource_type, origin or None
                        )
                        if (
                            routed_request.is_navigation_request()
                            and routed_request.resource_type == "document"
                        ):
                            navigation_urls.append(routed_request.url)
                            redirect_decision = policy.allow_redirect_count(max(0, len(navigation_urls) - 1))
                            if not redirect_decision.allowed:
                                blocked = redirect_decision
                                await route.abort("blockedbyclient")
                                return
                        if not request_decision.allowed:
                            blocked = request_decision
                            await route.abort("blockedbyclient")
                            return
                        await route.continue_()

                    page.on(
                        "download",
                        lambda download: download_tasks.append(
                            asyncio.create_task(self._store_download(download))
                        ),
                    )
                    page.on("crash", lambda: lifecycle_events.append({"type": "page_crashed"}))
                    await page.route("**/*", route_handler)
                    lifecycle_events.append({"type": "navigation_started", "url": request.url})
                    try:
                        response = await self._navigate_with_cancellation(page, request, policy)
                    except NavigationFailed as error:
                        if blocked:
                            raise BrowserPolicyBlocked(blocked.code, blocked.message) from error
                        raise
                    if blocked:
                        raise BrowserPolicyBlocked(blocked.code, blocked.message)
                    if page.is_closed():
                        raise PageCrashed("The page closed unexpectedly during navigation.")
                    if response and (content_length := response.headers.get("content-length")):
                        try:
                            if int(content_length) > self.settings.browser_max_response_bytes:
                                raise BrowserResourceLimit(
                                    "The navigation response exceeded its configured size limit."
                                )
                        except ValueError:
                            pass
                    redirect_chain: list[str] = []
                    if response:
                        current_request = response.request
                        while current_request:
                            redirect_chain.append(current_request.url)
                            current_request = current_request.redirected_from
                        redirect_chain.reverse()
                    for redirect_count, target_url in enumerate(redirect_chain[1:], start=1):
                        self._require(policy.allow_redirect_count(redirect_count))
                        self._require(
                            await policy.allow_navigation(target_url, redirect_chain[redirect_count - 1])
                        )
                    final_decision = await policy.allow_navigation(page.url, request.url)
                    self._require(final_decision)
                    title = await asyncio.wait_for(
                        page.title(), timeout=self.settings.browser_action_timeout_ms / 1000
                    )
                    metadata = NavigationMetadata(
                        requested_url=request.url,
                        final_url=page.url,
                        status=response.status if response else None,
                        content_type=response.headers.get("content-type") if response else None,
                        title=title[:500] if title else None,
                        viewport={
                            "width": self.settings.browser_viewport_width,
                            "height": self.settings.browser_viewport_height,
                        },
                        redirect_count=max(0, len(redirect_chain) - 1),
                        navigation_time_ms=int((time.monotonic() - started) * 1000),
                    )
                    lifecycle_events.append({"type": "navigation_completed", "url": metadata.final_url})
                    artifacts: list[BrowserArtifactResult] = []
                    if request.capture_screenshot:
                        artifacts.append(await self._screenshot(page, request.full_page_screenshot))
                    if download_tasks:
                        artifacts.extend(await asyncio.gather(*download_tasks))
                    return BrowserOperationResult(metadata, tuple(artifacts), tuple(lifecycle_events))
        except TimeoutError as error:
            raise BrowserTimeout("The browser operation exceeded its configured lifetime.") from error
        finally:
            await self._close_owned(page, context, browser, request)
            self.capacity.release()

    async def _navigate_with_cancellation(
        self, page: Page, request: BrowserOperationRequest, policy: BrowserPolicy
    ):
        navigation = asyncio.create_task(
            page.goto(
                request.url,
                wait_until="domcontentloaded",
                timeout=self.settings.browser_navigation_timeout_ms,
            )
        )
        try:
            while not navigation.done():
                if await policy.should_cancel(request.job_id):
                    navigation.cancel()
                    await asyncio.gather(navigation, return_exceptions=True)
                    raise BrowserCancelled("Browser work was cancelled during navigation.")
                await asyncio.sleep(0.1)
            return await navigation
        except PlaywrightTimeoutError as error:
            raise NavigationTimeout("Navigation exceeded its configured timeout.") from error
        except BrowserCancelled:
            raise
        except PlaywrightError as error:
            text = str(error).lower()
            if "crash" in text:
                raise BrowserCrashed("The browser process stopped during navigation.") from error
            raise NavigationFailed("The page could not be loaded safely.") from error
        finally:
            if not navigation.done():
                navigation.cancel()

    async def _screenshot(self, page: Page, full_page: bool) -> BrowserArtifactResult:
        try:
            image = await asyncio.wait_for(
                page.screenshot(type="png", full_page=full_page),
                timeout=self.settings.browser_action_timeout_ms / 1000,
            )
        except PlaywrightTimeoutError as error:
            raise BrowserTimeout("Screenshot capture exceeded its configured timeout.") from error
        if len(image) > self.settings.browser_max_screenshot_bytes:
            raise BrowserResourceLimit("The screenshot exceeded its configured size limit.")
        ref = await self.artifact_store.put(
            "browser_screenshot", bytes_stream(image), media_type="image/png", metadata={}
        )
        return BrowserArtifactResult("full_page_screenshot" if full_page else "viewport_screenshot", ref)

    async def _store_download(self, download: Download) -> BrowserArtifactResult:
        path = await download.path()
        if path is None:
            raise NavigationFailed("The browser download could not be captured safely.")

        async def download_stream() -> AsyncIterator[bytes]:
            total = 0
            with open(path, "rb") as handle:
                while chunk := await asyncio.to_thread(handle.read, 64 * 1024):
                    total += len(chunk)
                    if total > self.settings.browser_max_download_bytes:
                        raise DownloadTooLarge("The browser download exceeded its configured size limit.")
                    yield chunk

        ref = await self.artifact_store.put(
            "browser_download", download_stream(), media_type="application/octet-stream", metadata={}
        )
        return BrowserArtifactResult("download", ref)

    async def _close_owned(self, page, context, browser, request: BrowserOperationRequest) -> None:
        for resource, event_name in (
            (page, "browser.page.closed"),
            (context, "browser.context.closed"),
            (browser, "browser.closed"),
        ):
            if resource is None:
                continue
            try:
                await asyncio.wait_for(
                    resource.close(), timeout=self.settings.browser_shutdown_timeout_ms / 1000
                )
                log.info(event_name, job_id=request.job_id, operation_key=request.operation_key)
            except (PlaywrightError, TimeoutError):
                log.warning("browser.cleanup.failed", resource=event_name, job_id=request.job_id)

    @staticmethod
    def _require(decision: PolicyDecision) -> None:
        if not decision.allowed:
            if decision.code == "RESOURCE_LIMIT_EXCEEDED":
                raise BrowserResourceLimit(decision.message)
            raise BrowserPolicyBlocked(decision.code, decision.message)

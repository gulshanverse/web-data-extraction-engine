"""Stable, safe browser-runtime failures. Playwright details remain in protected logs."""

from __future__ import annotations

from wde_api.domain import DomainError, RetryableOperationError


class BrowserEngineError(DomainError):
    status_code = 422


class BrowserLaunchError(RetryableOperationError):
    code = "BROWSER_LAUNCH_FAILED"
    status_code = 503


class BrowserTimeout(BrowserEngineError):
    code = "BROWSER_TIMEOUT"


class NavigationTimeout(BrowserEngineError):
    code = "NAVIGATION_TIMEOUT"


class NavigationFailed(RetryableOperationError):
    code = "NAVIGATION_FAILED"
    status_code = 502


class BrowserCrashed(RetryableOperationError):
    code = "BROWSER_CRASHED"
    status_code = 503


class PageCrashed(RetryableOperationError):
    code = "PAGE_CRASHED"
    status_code = 503


class BrowserCancelled(BrowserEngineError):
    code = "BROWSER_CANCELLED"
    status_code = 409


class BrowserPolicyBlocked(BrowserEngineError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BrowserResourceLimit(BrowserEngineError):
    code = "RESOURCE_LIMIT_EXCEEDED"


class DownloadTooLarge(BrowserEngineError):
    code = "DOWNLOAD_TOO_LARGE"

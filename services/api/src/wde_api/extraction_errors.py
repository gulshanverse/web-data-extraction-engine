"""Stable Phase 6 extraction failures without validation semantics."""

from __future__ import annotations


class ExtractionError(Exception):
    code = "EXTRACTION_FAILED"
    retryable = False

    def __init__(self, message: str = "Extraction could not complete safely.") -> None:
        super().__init__(message)
        self.message = message


class ExtractionTimeout(ExtractionError):
    code = "EXTRACTION_TIMEOUT"
    retryable = True


class ExtractionBrowserFailed(ExtractionError):
    code = "EXTRACTION_BROWSER_FAILED"
    retryable = True


class ExtractionPolicyBlocked(ExtractionError):
    code = "EXTRACTION_POLICY_BLOCKED"


class ExtractionLimitReached(ExtractionError):
    code = "EXTRACTION_LIMIT_REACHED"


class ExtractionCancelled(ExtractionError):
    code = "EXTRACTION_CANCELLED"


class ExtractionInputInvalid(ExtractionError):
    code = "EXTRACTION_INPUT_INVALID"

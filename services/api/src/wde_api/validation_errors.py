"""Stable Phase 7 validation errors; invalid data is a result, not a worker failure."""

from __future__ import annotations


class ValidationEngineError(Exception):
    code = "VALIDATION_ENGINE_FAILED"
    retryable = False

    def __init__(self, message: str = "Validation could not complete safely.") -> None:
        super().__init__(message)
        self.message = message


class ValidationInfrastructureError(ValidationEngineError):
    code = "VALIDATION_INFRASTRUCTURE_FAILED"
    retryable = True


class ValidationCancelled(ValidationEngineError):
    code = "VALIDATION_CANCELLED"

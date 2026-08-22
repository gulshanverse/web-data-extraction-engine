"""Stable, safe errors emitted by the Phase 4 declarative planner."""

from __future__ import annotations


class PlannerError(Exception):
    code = "PLANNER_PROVIDER_ERROR"
    retryable = False

    def __init__(self, message: str = "Planner operation failed.") -> None:
        super().__init__(message)
        self.message = message


class PlannerInvalidOutput(PlannerError):
    code = "PLANNER_INVALID_OUTPUT"


class PlannerSchemaError(PlannerError):
    code = "PLANNER_SCHEMA_ERROR"


class PlannerTimeout(PlannerError):
    code = "PLANNER_TIMEOUT"
    retryable = True


class PlannerRateLimited(PlannerError):
    code = "PLANNER_RATE_LIMITED"
    retryable = True


class PlannerUnavailable(PlannerError):
    code = "PLANNER_UNAVAILABLE"
    retryable = True


class PlannerNotConfigured(PlannerUnavailable):
    """A safe terminal configuration failure that must not synthesize a plan."""

    retryable = False


class PlannerPolicyRejected(PlannerError):
    code = "PLANNER_POLICY_REJECTED"

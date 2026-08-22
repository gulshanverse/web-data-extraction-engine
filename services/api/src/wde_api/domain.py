"""Pure Phase 0 lifecycle rules. Browser, planner, discovery, extraction, validation, and export engines remain absent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from random import uniform


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    BROWSER_INITIALIZING = "BROWSER_INITIALIZING"
    DISCOVERING = "DISCOVERING"
    EXTRACTING = "EXTRACTING"
    VALIDATING = "VALIDATING"
    EXPORTING = "EXPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
ACTIVE_STATES = set(JobStatus) - TERMINAL_STATES - {JobStatus.QUEUED}
ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.PLANNING, JobStatus.CANCELLED},
    JobStatus.PLANNING: {JobStatus.BROWSER_INITIALIZING, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.BROWSER_INITIALIZING: {JobStatus.DISCOVERING, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.DISCOVERING: {JobStatus.EXTRACTING, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.EXTRACTING: {JobStatus.VALIDATING, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.VALIDATING: {JobStatus.EXPORTING, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.EXPORTING: {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
}
EVENT_FOR_TRANSITION = {
    (JobStatus.QUEUED, JobStatus.PLANNING): "planning_started",
    (JobStatus.PLANNING, JobStatus.BROWSER_INITIALIZING): "planning_completed",
    (JobStatus.BROWSER_INITIALIZING, JobStatus.DISCOVERING): "browser_started",
    (JobStatus.QUEUED, JobStatus.CANCELLED): "job_cancelled",
    (JobStatus.PLANNING, JobStatus.CANCELLED): "job_cancelled",
    (JobStatus.BROWSER_INITIALIZING, JobStatus.CANCELLED): "job_cancelled",
    (JobStatus.DISCOVERING, JobStatus.CANCELLED): "job_cancelled",
    (JobStatus.EXTRACTING, JobStatus.CANCELLED): "job_cancelled",
    (JobStatus.VALIDATING, JobStatus.CANCELLED): "job_cancelled",
    (JobStatus.EXPORTING, JobStatus.CANCELLED): "job_cancelled",
}


class DomainError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500
    retryable = False

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidTransition(DomainError):
    code = "INVALID_STATE_TRANSITION"
    status_code = 409


class JobCancelled(DomainError):
    code = "JOB_CANCELLED"
    status_code = 409


class RetryableOperationError(DomainError):
    retryable = True


def assert_transition(source: JobStatus, target: JobStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[source]:
        raise InvalidTransition(f"Cannot transition from {source} to {target}.")


def retry_delay_seconds(attempt: int, *, base_seconds: float = 1.0, maximum_seconds: float = 60.0) -> float:
    capped = min(maximum_seconds, base_seconds * (2 ** max(0, attempt - 1)))
    return capped + uniform(0, min(1.0, capped * 0.15))


@dataclass(frozen=True)
class OperationCommand:
    job_id: str
    project_id: str
    correlation_id: str
    operation_key: str
    attempt: int
    plan_version: int | None = None

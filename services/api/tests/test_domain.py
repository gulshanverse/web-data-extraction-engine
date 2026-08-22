import pytest
from wde_api.domain import InvalidTransition, JobStatus, assert_transition, retry_delay_seconds


def test_allows_documented_queued_to_planning_transition() -> None:
    assert_transition(JobStatus.QUEUED, JobStatus.PLANNING)


def test_retains_the_documented_browser_to_discovery_transition_for_phase_three() -> None:
    assert_transition(JobStatus.BROWSER_INITIALIZING, JobStatus.DISCOVERING)


def test_rejects_illegal_stale_transition() -> None:
    with pytest.raises(InvalidTransition):
        assert_transition(JobStatus.QUEUED, JobStatus.EXTRACTING)


def test_terminal_state_is_immutable() -> None:
    with pytest.raises(InvalidTransition):
        assert_transition(JobStatus.COMPLETED, JobStatus.QUEUED)


def test_retry_backoff_is_positive_and_bounded() -> None:
    assert 1 <= retry_delay_seconds(1) <= 2
    assert retry_delay_seconds(20) <= 61

from __future__ import annotations

import copy

import pytest
from planner_fixtures import options, valid_plan
from wde_api.planner_errors import PlannerPolicyRejected, PlannerSchemaError
from wde_api.planner_types import canonical_plan_json, plan_hash, validate_plan


def validate(raw: object):
    return validate_plan(
        raw,
        source_url="https://example.com/products",
        max_pages=100,
        max_records=10_000,
        max_fields=64,
        max_outputs=7,
        requested_options=options(),
        requested_outputs=["json"],
    )


def test_canonical_plan_hash_is_reproducible_and_independent_of_object_order() -> None:
    first = validate(valid_plan())
    second = validate(copy.deepcopy(valid_plan()))
    assert canonical_plan_json(first) == canonical_plan_json(second)
    assert plan_hash(first) == plan_hash(second)
    assert len(plan_hash(first)) == 64


@pytest.mark.parametrize(
    ("mutate", "error_type"),
    [
        (lambda raw: raw.update({"extra": "rejected"}), PlannerSchemaError),
        (lambda raw: raw["source"].update({"url": "https://other.example/"}), PlannerPolicyRejected),
        (lambda raw: raw["fields"][0].update({"type": "html"}), PlannerSchemaError),
        (
            lambda raw: raw["fields"][0].update({"description": "Use XPath for this value."}),
            PlannerSchemaError,
        ),
        (
            lambda raw: (
                raw["limits"].update({"max_pages": 21}),
                raw["navigation"].update({"max_pages": 21}),
            ),
            PlannerPolicyRejected,
        ),
        (lambda raw: raw.update({"outputs": ["csv"]}), PlannerPolicyRejected),
    ],
)
def test_plan_rejects_untrusted_or_noncanonical_output(mutate, error_type: type[Exception]) -> None:
    raw = valid_plan()
    mutate(raw)
    with pytest.raises(error_type):
        validate(raw)


def test_ambiguous_request_can_record_no_fields_without_execution_details() -> None:
    raw = valid_plan(fields=[])
    raw["ambiguities"] = [{"message": "The requested record fields require clarification."}]
    plan = validate(raw)
    assert plan.fields == []
    assert plan.ambiguities[0].message.startswith("The requested")


def test_empty_fields_without_ambiguity_are_rejected() -> None:
    with pytest.raises(PlannerSchemaError):
        validate(valid_plan(fields=[]))

from __future__ import annotations

from planner_fixtures import valid_plan
from wde_api.planner_types import CanonicalPlan
from wde_api.validation_service import ValidationService


def plan() -> CanonicalPlan:
    raw = valid_plan()
    raw["fields"] = [
        {"name": "name", "label": "Name", "type": "string", "required": True, "description": "Name"},
        {"name": "price", "label": "Price", "type": "currency", "required": True, "description": "Price"},
        {"name": "url", "label": "URL", "type": "url", "required": False, "description": "URL"},
    ]
    return CanonicalPlan.model_validate(raw)


def record(*, price: object = 9.99, raw: str = "$9.99", evidence: object = None) -> dict[str, object]:
    evidence = evidence if evidence is not None else {"source_text": raw, "location": "table[0].row[0]"}
    return {
        "record_id": "r-1",
        "provenance": {"plan_version": "1", "page_id": "page-1", "canonical_url": "https://example.com/p/1"},
        "fields": {
            "name": {
                "raw": "Widget",
                "value": "Widget",
                "evidence": {"source_text": "Widget", "location": "table[0].row[0]"},
            },
            "price": {"raw": raw, "value": price, "evidence": evidence},
            "url": {
                "raw": "/p/1",
                "value": "https://example.com/p/1",
                "evidence": {"source_text": "/p/1", "location": "table[0].row[0]"},
            },
        },
    }


def test_valid_record_has_high_quality_and_versioned_outcomes() -> None:
    result = ValidationService().validate(plan=plan(), record=record())
    assert result.status == "PASS" and result.quality == "HIGH"
    assert result.fields["price"].status == "PASS"


def test_required_missing_and_bad_currency_are_invalid_without_mutating_input() -> None:
    source = record(price="free", raw="free")
    source["fields"]["name"]["value"] = None  # type: ignore[index]
    original = repr(source)
    result = ValidationService().validate(plan=plan(), record=source)
    assert result.quality == "INVALID" and result.fields["name"].status == "FAIL"
    assert repr(source) == original


def test_optional_missing_and_evidence_absence_produce_deterministic_warnings() -> None:
    source = record()
    source["fields"]["url"]["value"] = None  # type: ignore[index]
    source["fields"]["price"]["evidence"] = None  # type: ignore[index]
    result = ValidationService().validate(plan=plan(), record=source)
    assert result.quality == "MEDIUM"
    assert result.fields["url"].status == "WARN"


def test_invalid_url_date_and_normalization_consistency_fail() -> None:
    source = record(price=999, raw="$9.99")
    source["fields"]["url"]["value"] = "javascript:alert(1)"  # type: ignore[index]
    result = ValidationService().validate(plan=plan(), record=source)
    assert result.quality == "INVALID"
    assert any(
        rule.rule_id == "normalization.v1" and rule.status == "FAIL" for rule in result.fields["price"].rules
    )
    assert any(rule.status == "FAIL" for rule in result.fields["url"].rules)

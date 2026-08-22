"""Deterministic Phase 7 validation. It evaluates immutable extraction payloads and never repairs them."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from urllib.parse import urlparse

from wde_api.extraction_service import normalize
from wde_api.planner_types import CanonicalPlan
from wde_api.validation_types import FieldValidation, RecordValidation, RuleOutcome

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PLACEHOLDER = {"n/a", "na", "unknown", "not available", "—"}


def _status(outcomes: list[RuleOutcome]) -> str:
    statuses = {outcome.status for outcome in outcomes}
    if "FAIL" in statuses:
        return "FAIL"
    if "UNRESOLVED" in statuses:
        return "UNRESOLVED"
    if "WARN" in statuses:
        return "WARN"
    if "PASS" in statuses:
        return "PASS"
    return "SKIPPED"


class ValidationService:
    """Rule registry order is stable: required, type/format, normalization, evidence, provenance, cross-field."""

    def validate(self, *, plan: CanonicalPlan, record: dict[str, object]) -> RecordValidation:
        fields_payload = record.get("fields", {})
        fields_payload = fields_payload if isinstance(fields_payload, dict) else {}
        result_fields: dict[str, FieldValidation] = {}
        all_outcomes: list[RuleOutcome] = []
        for definition in plan.fields:
            candidate = fields_payload.get(definition.name, {})
            candidate = candidate if isinstance(candidate, dict) else {}
            outcomes = self._field_rules(
                definition.name, definition.type, definition.required, candidate, record
            )
            field_status = _status(outcomes)
            result_fields[definition.name] = FieldValidation(definition.name, field_status, tuple(outcomes))
            all_outcomes.extend(outcomes)
        record_rules = self._record_rules(plan, record, result_fields)
        all_outcomes.extend(record_rules)
        summary = {
            key.lower(): sum(1 for outcome in all_outcomes if outcome.status == key)
            for key in ("PASS", "FAIL", "WARN", "UNRESOLVED")
        }
        overall = _status(all_outcomes)
        quality = self._quality(all_outcomes, result_fields)
        return RecordValidation(
            record_id=str(record.get("record_id", "")),
            plan_version=plan.plan_version,
            status=overall,
            quality=quality,
            fields=result_fields,
            record_rules=tuple(record_rules),
            summary=summary,
        )

    def _field_rules(
        self,
        name: str,
        field_type: str,
        required: bool,
        candidate: dict[str, object],
        record: dict[str, object],
    ) -> list[RuleOutcome]:
        value = candidate.get("value")
        raw = candidate.get("raw")
        missing = value is None or (isinstance(value, str) and not value.strip())
        outcomes: list[RuleOutcome] = [
            RuleOutcome(
                "required.v1",
                "FAIL" if required and missing else "PASS",
                "Required value is missing." if required and missing else None,
            )
        ]
        if missing:
            if not required:
                outcomes.append(RuleOutcome("optional_missing.v1", "WARN", "Optional value is missing."))
            return outcomes
        outcomes.append(self._type_rule(field_type, value))
        outcomes.append(self._format_rule(field_type, value))
        if raw is not None:
            expected = normalize(
                str(raw), field_type, base_url=str(record.get("provenance", {}).get("canonical_url", ""))
            )
            outcomes.append(
                RuleOutcome(
                    "normalization.v1",
                    "PASS" if expected == value else "FAIL",
                    None if expected == value else "Normalized value is inconsistent with the raw value.",
                )
            )
        evidence = candidate.get("evidence")
        if evidence is None:
            outcomes.append(RuleOutcome("evidence.v1", "WARN", "Extraction evidence is absent."))
        elif isinstance(evidence, dict):
            source_text = evidence.get("source_text")
            location = evidence.get("location")
            bounded = (
                isinstance(source_text, str)
                and len(source_text) <= 500
                and isinstance(location, str)
                and bool(location)
            )
            outcomes.append(
                RuleOutcome(
                    "evidence.v1",
                    "PASS" if bounded else "FAIL",
                    None if bounded else "Evidence is malformed or exceeds its bound.",
                )
            )
        else:
            outcomes.append(RuleOutcome("evidence.v1", "FAIL", "Evidence is malformed."))
        return outcomes

    @staticmethod
    def _type_rule(field_type: str, value: object) -> RuleOutcome:
        numeric = (
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
        )
        valid = {
            "string": isinstance(value, str),
            "text": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": numeric,
            "currency": numeric,
            "boolean": isinstance(value, bool),
            "url": isinstance(value, str),
            "email": isinstance(value, str),
            "date": isinstance(value, str),
            "datetime": isinstance(value, str),
        }.get(field_type, False)
        return RuleOutcome(
            f"type.{field_type}.v1",
            "PASS" if valid else "FAIL",
            None if valid else f"Value does not match declared {field_type} type.",
        )

    @staticmethod
    def _format_rule(field_type: str, value: object) -> RuleOutcome:
        try:
            if field_type == "url":
                parsed = urlparse(str(value))
                valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            elif field_type == "email":
                valid = bool(_EMAIL.fullmatch(str(value)))
            elif field_type == "date":
                date.fromisoformat(str(value))
                valid = True
            elif field_type == "datetime":
                datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                valid = True
            elif field_type in {"string", "text"}:
                valid = bool(str(value).strip())
            else:
                return RuleOutcome("format.skipped.v1", "SKIPPED")
        except ValueError:
            valid = False
        return RuleOutcome(
            f"format.{field_type}.v1",
            "PASS" if valid else "FAIL",
            None if valid else f"Value has invalid {field_type} format.",
        )

    @staticmethod
    def _record_rules(
        plan: CanonicalPlan, record: dict[str, object], fields: dict[str, FieldValidation]
    ) -> list[RuleOutcome]:
        provenance = record.get("provenance", {})
        provenance = provenance if isinstance(provenance, dict) else {}
        rules = [
            RuleOutcome(
                "provenance.v1",
                "PASS"
                if provenance.get("plan_version") == str(plan.plan_version) and provenance.get("page_id")
                else "FAIL",
                None
                if provenance.get("plan_version") == str(plan.plan_version) and provenance.get("page_id")
                else "Record provenance is inconsistent with the canonical plan.",
            )
        ]
        payload = record.get("fields", {}) if isinstance(record.get("fields"), dict) else {}
        pairs = (
            ("start_date", "end_date"),
            ("min_price", "max_price"),
            ("discounted_price", "original_price"),
        )
        for low, high in pairs:
            if low in payload and high in payload:
                left, right = payload[low].get("value"), payload[high].get("value")
                if left is not None and right is not None and left > right:
                    rules.append(
                        RuleOutcome(f"cross_field.{low}.{high}.v1", "FAIL", f"{low} must not exceed {high}.")
                    )
        return rules

    @staticmethod
    def _quality(outcomes: list[RuleOutcome], fields: dict[str, FieldValidation]) -> str:
        statuses = {outcome.status for outcome in outcomes}
        if "FAIL" in statuses:
            return "INVALID"
        if "UNRESOLVED" in statuses:
            return "UNRESOLVED"
        if "WARN" in statuses:
            return "MEDIUM"
        return "HIGH"

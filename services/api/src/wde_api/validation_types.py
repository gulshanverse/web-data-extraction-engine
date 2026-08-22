"""Versioned, deterministic Phase 7 validation result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ValidationStatus = Literal["PASS", "FAIL", "WARN", "UNRESOLVED", "SKIPPED"]
Quality = Literal["HIGH", "MEDIUM", "LOW", "INVALID", "UNRESOLVED"]
VALIDATION_SCHEMA_VERSION = "validation.v1"
VALIDATION_RULESET_VERSION = "rules.v1"


@dataclass(frozen=True)
class RuleOutcome:
    rule_id: str
    status: ValidationStatus
    message: str | None = None


@dataclass(frozen=True)
class FieldValidation:
    field: str
    status: ValidationStatus
    rules: tuple[RuleOutcome, ...]


@dataclass(frozen=True)
class RecordValidation:
    record_id: str
    plan_version: int
    status: ValidationStatus
    quality: Quality
    fields: dict[str, FieldValidation]
    record_rules: tuple[RuleOutcome, ...]
    summary: dict[str, int]

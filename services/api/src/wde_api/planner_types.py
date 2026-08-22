"""Versioned, declarative Phase 4 plan models; no website access or extraction instructions exist here."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wde_api.planner_errors import PlannerPolicyRejected, PlannerSchemaError

PLAN_SCHEMA_VERSION = "plan.v1"
PROMPT_VERSION = "planner.system.v1"
FIELD_TYPES = {
    "string",
    "integer",
    "number",
    "boolean",
    "date",
    "datetime",
    "url",
    "email",
    "currency",
    "text",
}
OUTPUT_FORMATS = {"excel", "csv", "json", "pdf", "docx", "markdown", "txt", "html"}
_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FORBIDDEN = re.compile(
    r"(selector|xpath|javascript:|<script|\b(shell|sql|python)\b|system prompt|ignore.*instruction)", re.I
)
_OUTPUT_ALIASES = {"xlsx": "excel", "md": "markdown"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PlanField(StrictModel):
    name: str
    label: str = Field(min_length=1, max_length=120)
    type: Literal[
        "string", "integer", "number", "boolean", "date", "datetime", "url", "email", "currency", "text"
    ]
    required: bool
    description: str = Field(min_length=1, max_length=500)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    example_value: str | None = Field(default=None, max_length=200)
    normalization_hint: str | None = Field(default=None, max_length=300)

    @field_validator("name")
    @classmethod
    def stable_name(cls, value: str) -> str:
        if not _SAFE_NAME.fullmatch(value):
            raise ValueError("Field names must be stable lower_snake_case identifiers.")
        return value

    @model_validator(mode="after")
    def declarative_only(self) -> PlanField:
        values = [self.label, self.description, self.normalization_hint or "", *self.aliases]
        if _FORBIDDEN.search(" ".join(values)):
            raise ValueError("Field definitions must be semantic and declarative.")
        return self


class SourceIntent(StrictModel):
    url: str
    scope: Literal["site", "page"] = "site"

    @field_validator("url")
    @classmethod
    def source_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Source URL must be absolute HTTP(S).")
        return value


class Intent(StrictModel):
    summary: str = Field(min_length=1, max_length=500)
    objective: Literal["structured_records"] = "structured_records"

    @field_validator("summary")
    @classmethod
    def declarative_summary(cls, value: str) -> str:
        if _FORBIDDEN.search(value):
            raise ValueError("Intent must remain declarative.")
        return value


class NavigationIntent(StrictModel):
    follow_pagination: bool = False
    pagination_likely: bool = False
    follow_relevant_links: bool = False
    relevant_link_purpose: str | None = Field(default=None, max_length=300)
    max_pages: int = Field(ge=1)

    @field_validator("relevant_link_purpose")
    @classmethod
    def declarative_link_purpose(cls, value: str | None) -> str | None:
        if value and _FORBIDDEN.search(value):
            raise ValueError("Link intent must remain declarative.")
        return value


class DeduplicationIntent(StrictModel):
    enabled: bool = True
    keys: list[str] = Field(default_factory=list, max_length=5)


class ValidationExpectation(StrictModel):
    field: str = Field(min_length=1, max_length=64)
    rule: str = Field(min_length=1, max_length=300)

    @field_validator("rule")
    @classmethod
    def declarative_rule(cls, value: str) -> str:
        if _FORBIDDEN.search(value):
            raise ValueError("Validation intent must remain declarative.")
        return value


class ValidationIntent(StrictModel):
    enabled: bool = True
    expectations: list[ValidationExpectation] = Field(default_factory=list, max_length=64)


class Limits(StrictModel):
    max_pages: int = Field(ge=1)
    max_records: int = Field(ge=1)


class Assumption(StrictModel):
    statement: str = Field(min_length=1, max_length=500)
    confidence: Literal["low", "medium", "high"] = "medium"


class Ambiguity(StrictModel):
    message: str = Field(min_length=1, max_length=500)


class CanonicalPlan(StrictModel):
    schema_version: Literal["plan.v1"] = PLAN_SCHEMA_VERSION
    plan_version: int = Field(ge=1)
    source: SourceIntent
    intent: Intent
    fields: list[PlanField] = Field(max_length=64)
    navigation: NavigationIntent
    deduplication: DeduplicationIntent
    validation: ValidationIntent
    limits: Limits
    outputs: list[Literal["excel", "csv", "json", "pdf", "docx", "markdown", "txt", "html"]] = Field(
        max_length=8
    )
    assumptions: list[Assumption] = Field(default_factory=list, max_length=32)
    ambiguities: list[Ambiguity] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def coherent(self) -> CanonicalPlan:
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Fields must have unique names.")
        if len(self.outputs) != len(set(self.outputs)):
            raise ValueError("Outputs must be unique.")
        if not self.fields and not self.ambiguities:
            raise ValueError("An empty field list requires a recorded ambiguity.")
        if self.navigation.max_pages != self.limits.max_pages:
            raise ValueError("Navigation and limit page bounds must agree.")
        return self


def canonical_plan_json(plan: CanonicalPlan) -> str:
    """Return stable JSON independent of database IDs and timestamps."""
    return json.dumps(plan.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def plan_hash(plan: CanonicalPlan) -> str:
    return hashlib.sha256(canonical_plan_json(plan).encode("utf-8")).hexdigest()


def canonical_output_formats(outputs: list[str]) -> list[str]:
    return [_OUTPUT_ALIASES.get(output.lower().lstrip("."), output.lower().lstrip(".")) for output in outputs]


def validate_plan(
    raw: object,
    *,
    source_url: str,
    max_pages: int,
    max_records: int,
    max_fields: int,
    max_outputs: int,
    requested_options: dict[str, object] | None = None,
    requested_outputs: list[str] | None = None,
) -> CanonicalPlan:
    """Parse declarative model output and enforce server- and request-owned bounds."""
    try:
        plan = CanonicalPlan.model_validate(raw)
    except Exception as exc:
        raise PlannerSchemaError("The planner returned an invalid structured plan.") from exc
    if plan.plan_version != 1:
        raise PlannerPolicyRejected("Planner output cannot select a plan version.")
    if plan.source.url != source_url:
        raise PlannerPolicyRejected("Planner output cannot alter the requested source URL.")
    if len(plan.fields) > max_fields or len(plan.outputs) > max_outputs:
        raise PlannerSchemaError("Planner output exceeds server field or output limits.")
    if plan.limits.max_pages > max_pages or plan.limits.max_records > max_records:
        raise PlannerPolicyRejected("Planner output exceeds server resource limits.")
    if requested_outputs is not None and plan.outputs != canonical_output_formats(requested_outputs):
        raise PlannerPolicyRejected("Planner output cannot alter the requested output formats.")
    if requested_options is not None:
        expected_pages = int(requested_options["max_pages"])
        expected_records = int(requested_options["max_records"])
        if plan.limits.max_pages != expected_pages or plan.limits.max_records != expected_records:
            raise PlannerPolicyRejected("Planner output cannot alter the requested resource limits.")
        if plan.navigation.follow_pagination != bool(requested_options["follow_pagination"]):
            raise PlannerPolicyRejected("Planner output cannot alter pagination intent.")
        if plan.navigation.follow_relevant_links != bool(requested_options["follow_relevant_links"]):
            raise PlannerPolicyRejected("Planner output cannot alter relevant-link intent.")
        if plan.deduplication.enabled != bool(requested_options["deduplicate"]):
            raise PlannerPolicyRejected("Planner output cannot alter deduplication intent.")
        if plan.validation.enabled != bool(requested_options["validate"]):
            raise PlannerPolicyRejected("Planner output cannot alter validation intent.")
    return plan

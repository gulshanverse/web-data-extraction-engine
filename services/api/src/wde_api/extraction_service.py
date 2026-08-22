"""Deterministic, plan-driven Phase 6 extraction strategies; no model provider, validation, or export behavior."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin

from wde_api.extraction_types import (
    ContentBlockSignal,
    ExtractedField,
    ExtractedRecord,
    ExtractionDocument,
    ExtractionResult,
    FieldEvidence,
    TableSignal,
)
from wde_api.planner_types import CanonicalPlan, PlanField

_WHITESPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"[-+]?\d+(?:[,.]\d+)?")
_EMAIL = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)


def _text(value: object) -> str:
    return _WHITESPACE.sub(" ", str(value or "")).strip()


def _aliases(field: PlanField) -> set[str]:
    return {item.lower() for item in [field.name, field.label, *field.aliases] if item}


def normalize(value: str | None, field_type: str, *, base_url: str) -> Any:
    """Perform bounded, reversible-as-possible normalization; malformed values remain raw strings or None."""
    text = _text(value)
    if not text:
        return None
    if field_type in {"string", "text"}:
        return text
    if field_type in {"integer", "number", "currency"}:
        match = _NUMBER.search(text.replace(",", ""))
        if not match:
            return None
        try:
            number = Decimal(match.group(0))
        except InvalidOperation:
            return None
        return int(number) if field_type == "integer" and number == number.to_integral() else float(number)
    if field_type == "boolean":
        lowered = text.lower()
        if lowered in {"true", "yes", "in stock", "available", "1"}:
            return True
        if lowered in {"false", "no", "out of stock", "unavailable", "0"}:
            return False
        return None
    if field_type == "url":
        candidate = urljoin(base_url, text)
        return candidate if candidate.startswith(("https://", "http://")) else None
    if field_type == "email":
        match = _EMAIL.search(text)
        return match.group(0).lower() if match else None
    if field_type in {"date", "datetime"}:
        for parser in (datetime.fromisoformat, date.fromisoformat):
            try:
                parsed = parser(text.replace("Z", "+00:00"))
                if field_type == "date":
                    return parsed.date().isoformat() if isinstance(parsed, datetime) else parsed.isoformat()
                return (
                    parsed.isoformat() if isinstance(parsed, datetime) else f"{parsed.isoformat()}T00:00:00"
                )
            except ValueError:
                continue
        return None
    return text


class ExtractionService:
    """Priority: JSON-LD/OpenGraph, tables, repeated blocks, then a single detail-page representation."""

    def __init__(self, *, max_evidence_chars: int = 500) -> None:
        self.max_evidence_chars = max_evidence_chars

    def extract(
        self, *, plan: CanonicalPlan, page_url: str, page_id: str, document: ExtractionDocument
    ) -> ExtractionResult:
        warnings: list[str] = []
        records = self._structured_records(plan, page_url, page_id, document, warnings)
        if not records:
            records = self._table_records(plan, page_url, page_id, document)
        if not records:
            records = self._block_records(plan, page_url, page_id, document)
        if not records:
            records = (self._detail_record(plan, page_url, page_id, document),)
        return ExtractionResult(
            tuple(records[: plan.limits.max_records]), tuple(warnings), document.truncated
        )

    def _structured_records(
        self,
        plan: CanonicalPlan,
        page_url: str,
        page_id: str,
        document: ExtractionDocument,
        warnings: list[str],
    ) -> tuple[ExtractedRecord, ...]:
        entities: list[tuple[dict[str, Any], str]] = []
        for index, raw in enumerate(document.json_ld):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                warnings.append("malformed_json_ld")
                continue
            if isinstance(value, list):
                entities.extend((item, f"json_ld[{index}]") for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                graph = value.get("@graph")
                if isinstance(graph, list):
                    entities.extend(
                        (item, f"json_ld[{index}].@graph") for item in graph if isinstance(item, dict)
                    )
                entities.append((value, f"json_ld[{index}]"))
        output = [
            self._record_from_mapping(plan, page_url, page_id, entity, "structured_data", location)
            for entity, location in entities
        ]
        return tuple(record for record in output if self._has_value(record))

    def _table_records(
        self, plan: CanonicalPlan, page_url: str, page_id: str, document: ExtractionDocument
    ) -> tuple[ExtractedRecord, ...]:
        records: list[ExtractedRecord] = []
        for table_index, table in enumerate(document.tables):
            mapping = self._header_mapping(plan, table)
            if not mapping:
                continue
            for row_index, row in enumerate(table.rows):
                source = {field.name: row[column] for field, column in mapping if column < len(row)}
                records.append(
                    self._record_from_mapping(
                        plan, page_url, page_id, source, "table", f"table[{table_index}].row[{row_index}]"
                    )
                )
        return tuple(record for record in records if self._has_value(record))

    def _block_records(
        self, plan: CanonicalPlan, page_url: str, page_id: str, document: ExtractionDocument
    ) -> tuple[ExtractedRecord, ...]:
        candidates = [block for block in document.blocks if len(block.text) >= 3]
        if len(candidates) < 2:
            return ()
        records = [
            self._record_from_block(plan, page_url, page_id, block, index)
            for index, block in enumerate(candidates)
        ]
        meaningful = tuple(record for record in records if self._has_value(record))
        return meaningful if len(meaningful) >= 2 else ()

    def _detail_record(
        self, plan: CanonicalPlan, page_url: str, page_id: str, document: ExtractionDocument
    ) -> ExtractedRecord:
        source: dict[str, str] = dict(document.open_graph or {})
        source["url"] = page_url
        source["text"] = document.page_text
        return self._record_from_mapping(plan, page_url, page_id, source, "detail_page", "document")

    def _record_from_block(
        self, plan: CanonicalPlan, page_url: str, page_id: str, block: ContentBlockSignal, index: int
    ) -> ExtractedRecord:
        source = {"text": block.text, "url": block.href or page_url, "image": block.image_url or ""}
        return self._record_from_mapping(plan, page_url, page_id, source, "repeated_block", f"block[{index}]")

    def _record_from_mapping(
        self,
        plan: CanonicalPlan,
        page_url: str,
        page_id: str,
        source: dict[str, Any],
        strategy: str,
        location: str,
    ) -> ExtractedRecord:
        fields: dict[str, ExtractedField] = {}
        for field in plan.fields:
            raw = self._lookup(field, source)
            if raw is None and field.type in {"string", "text"} and source.get("text"):
                raw = str(source["text"])
            if raw is None and field.type == "url" and source.get("url"):
                raw = str(source["url"])
            normalized = normalize(str(raw), field.type, base_url=page_url) if raw is not None else None
            fields[field.name] = ExtractedField(
                raw_value=_text(raw) if raw is not None else None,
                value=normalized,
                field_type=field.type,
                strategy=strategy,  # type: ignore[arg-type]
                confidence="high" if strategy == "structured_data" else "medium",
                missing=normalized is None,
                evidence=FieldEvidence(
                    _text(raw)[: self.max_evidence_chars] if raw is not None else None, location
                )
                if raw is not None
                else None,
            )
        identity_seed = "|".join(
            str(fields[name].value or "") for name in [field.name for field in plan.fields]
        )
        identity = hashlib.sha256(f"{page_id}|{page_url}|{identity_seed}".encode()).hexdigest()
        return ExtractedRecord(
            identity=identity,
            strategy=strategy,  # type: ignore[arg-type]
            fields=fields,
            confidence=0.95 if strategy == "structured_data" else 0.7,
            provenance={
                "source_url": page_url,
                "canonical_url": page_url,
                "page_id": page_id,
                "plan_version": str(plan.plan_version),
            },
        )

    @staticmethod
    def _header_mapping(plan: CanonicalPlan, table: TableSignal) -> tuple[tuple[PlanField, int], ...]:
        result: list[tuple[PlanField, int]] = []
        headers = [_text(header).lower() for header in table.headers]
        for field in plan.fields:
            for index, header in enumerate(headers):
                if header in _aliases(field) or any(alias in header for alias in _aliases(field)):
                    result.append((field, index))
                    break
        return tuple(result)

    @staticmethod
    def _lookup(field: PlanField, source: dict[str, Any]) -> Any | None:
        aliases = _aliases(field)
        for key, value in source.items():
            normalized = str(key).lower().replace("@", "")
            if normalized in aliases or any(alias in normalized for alias in aliases):
                if isinstance(value, dict):
                    for nested in ("price", "value", "name", "url"):
                        if nested in value:
                            return value[nested]
                return value
            if isinstance(value, dict):
                nested_value = ExtractionService._lookup(field, value)
                if nested_value is not None:
                    return nested_value
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        nested_value = ExtractionService._lookup(field, item)
                        if nested_value is not None:
                            return nested_value
        return None

    @staticmethod
    def _has_value(record: ExtractedRecord) -> bool:
        return any(field.value is not None for field in record.fields.values())

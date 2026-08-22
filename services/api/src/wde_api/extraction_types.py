"""Typed Phase 6 extraction inputs and outputs; values are unvalidated evidence-backed candidates only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ExtractionStrategyName = Literal["structured_data", "table", "repeated_block", "detail_page", "semantic_text"]


@dataclass(frozen=True)
class TableSignal:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ContentBlockSignal:
    tag: str
    text: str
    href: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class ExtractionDocument:
    page_text: str = ""
    json_ld: tuple[str, ...] = ()
    open_graph: dict[str, str] | None = None
    tables: tuple[TableSignal, ...] = ()
    blocks: tuple[ContentBlockSignal, ...] = ()
    truncated: bool = False


@dataclass(frozen=True)
class FieldEvidence:
    source_text: str | None
    location: str
    attribute: str | None = None
    structured_path: str | None = None


@dataclass(frozen=True)
class ExtractedField:
    raw_value: str | None
    value: Any
    field_type: str
    strategy: ExtractionStrategyName
    confidence: Literal["high", "medium", "low"]
    missing: bool
    evidence: FieldEvidence | None


@dataclass(frozen=True)
class ExtractedRecord:
    identity: str
    strategy: ExtractionStrategyName
    fields: dict[str, ExtractedField]
    confidence: float
    provenance: dict[str, str]


@dataclass(frozen=True)
class ExtractionResult:
    records: tuple[ExtractedRecord, ...]
    warnings: tuple[str, ...]
    document_truncated: bool

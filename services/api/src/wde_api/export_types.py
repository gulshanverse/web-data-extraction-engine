"""Canonical Phase 8 export data contracts shared by every format writer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ExportFormat = Literal["xlsx", "csv", "json"]
RecordPolicy = Literal["ALL_RECORDS", "VALID_ONLY", "VALID_AND_WARNINGS"]
EXPORT_SCHEMA_VERSION = "export.v1"


@dataclass(frozen=True)
class ExportOptions:
    record_policy: RecordPolicy = "ALL_RECORDS"
    include_validation_metadata: bool = False
    include_provenance_metadata: bool = False


@dataclass(frozen=True)
class CanonicalExportDataset:
    fields: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    validation_run_id: str
    plan_version: int
    options: ExportOptions

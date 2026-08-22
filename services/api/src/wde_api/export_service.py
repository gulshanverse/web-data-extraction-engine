"""Phase 8 canonical dataset builder and deterministic XLSX, CSV, JSON writers."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Protocol

from openpyxl import Workbook
from openpyxl.styles import Font

from wde_api.export_errors import ExportTooLarge, ExportUnsupportedFormat
from wde_api.export_types import EXPORT_SCHEMA_VERSION, CanonicalExportDataset, ExportFormat, ExportOptions
from wde_api.planner_types import CanonicalPlan
from wde_api.storage import ArtifactRef, LocalArtifactStore

_FORMULA_PREFIXES = ("=", "+", "-", "@")
_MEDIA = {
    "csv": ("text/csv", ".csv"),
    "json": ("application/json", ".json"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
}


def _safe_spreadsheet(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _flat(value: Any, *, spreadsheet: bool) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _safe_spreadsheet(value) if spreadsheet else value


class ExportWriter(Protocol):
    format: ExportFormat
    media_type: str
    extension: str

    def write(self, dataset: CanonicalExportDataset) -> bytes: ...


class CsvExporter:
    format: ExportFormat = "csv"
    media_type, extension = _MEDIA["csv"]

    def write(self, dataset: CanonicalExportDataset) -> bytes:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            buffer, fieldnames=list(dataset.fields), lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        for row in dataset.rows:
            writer.writerow(
                {field: _flat(row.get(field), spreadsheet=True) or "" for field in dataset.fields}
            )
        return buffer.getvalue().encode("utf-8")


class JsonExporter:
    format: ExportFormat = "json"
    media_type, extension = _MEDIA["json"]

    def write(self, dataset: CanonicalExportDataset) -> bytes:
        records = [{field: row.get(field) for field in dataset.fields} for row in dataset.rows]
        payload = {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "format": "json",
            "record_count": len(records),
            "fields": list(dataset.fields),
            "validation_run_id": dataset.validation_run_id,
            "plan_version": dataset.plan_version,
            "records": records,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=False, indent=2, default=str).encode("utf-8")


class XlsxExporter:
    format: ExportFormat = "xlsx"
    media_type, extension = _MEDIA["xlsx"]

    def write(self, dataset: CanonicalExportDataset) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Data"
        sheet.append(list(dataset.fields))
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for row in dataset.rows:
            sheet.append([_flat(row.get(field), spreadsheet=True) for field in dataset.fields])
        for column in sheet.columns:
            width = min(60, max(10, max(len(str(cell.value or "")) for cell in column) + 2))
            sheet.column_dimensions[column[0].column_letter].width = width
        if dataset.options.include_validation_metadata:
            summary = workbook.create_sheet("Validation Summary")
            summary.append(["metric", "value"])
            summary.append(["total_records", len(dataset.rows)])
            summary.append(["validation_run_id", dataset.validation_run_id])
            summary.append(["plan_version", dataset.plan_version])
        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue()


WRITERS: dict[str, ExportWriter] = {
    writer.format: writer for writer in (CsvExporter(), JsonExporter(), XlsxExporter())
}


def build_dataset(
    *,
    plan: CanonicalPlan,
    validation_run_id: str,
    records: list[dict[str, Any]],
    options: ExportOptions,
    max_records: int,
) -> CanonicalExportDataset:
    if len(records) > max_records:
        raise ExportTooLarge("Export dataset exceeds the configured record limit.")
    fields = tuple(field.name for field in plan.fields)
    rows: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: str(item.get("record_identity", ""))):
        status = str(record.get("validation_status", ""))
        if options.record_policy == "VALID_ONLY" and status != "PASS":
            continue
        if options.record_policy == "VALID_AND_WARNINGS" and status not in {"PASS", "WARN"}:
            continue
        values = record.get("fields", {})
        values = values if isinstance(values, dict) else {}
        row = {
            field: values.get(field, {}).get("value") if isinstance(values.get(field), dict) else None
            for field in fields
        }
        if options.include_validation_metadata:
            row.update({"validation_status": status, "quality": record.get("quality")})
        if options.include_provenance_metadata:
            row["record_identity"] = record.get("record_identity")
        rows.append(row)
    extras = ("validation_status", "quality") if options.include_validation_metadata else ()
    extras += ("record_identity",) if options.include_provenance_metadata else ()
    return CanonicalExportDataset(
        fields=fields + extras,
        rows=tuple(rows),
        validation_run_id=validation_run_id,
        plan_version=plan.plan_version,
        options=options,
    )


def writer_for(format_name: str) -> ExportWriter:
    try:
        return WRITERS[format_name]
    except KeyError as exc:
        raise ExportUnsupportedFormat("Only xlsx, csv, and json exports are supported.") from exc


async def store_export(
    store: LocalArtifactStore,
    *,
    dataset: CanonicalExportDataset,
    format_name: str,
    artifact_type: str = "export",
) -> ArtifactRef:
    """Write a fully-built bounded export through the existing storage port only."""
    writer = writer_for(format_name)
    data = writer.write(dataset)

    async def stream():
        yield data

    return await store.put(
        artifact_type,
        stream(),
        media_type=writer.media_type,
        metadata={"format": format_name, "schema_version": EXPORT_SCHEMA_VERSION},
    )

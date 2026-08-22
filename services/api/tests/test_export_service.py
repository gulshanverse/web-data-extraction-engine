from __future__ import annotations

import csv
import io
import json

from openpyxl import load_workbook
from planner_fixtures import valid_plan
from wde_api.export_service import build_dataset, writer_for
from wde_api.export_types import ExportOptions
from wde_api.planner_types import CanonicalPlan


def plan() -> CanonicalPlan:
    raw = valid_plan()
    raw["fields"] = [
        {"name": "name", "label": "Name", "type": "string", "required": True, "description": "Name"},
        {"name": "price", "label": "Price", "type": "currency", "required": False, "description": "Price"},
    ]
    return CanonicalPlan.model_validate(raw)


def records() -> list[dict[str, object]]:
    return [
        {
            "record_identity": "b",
            "validation_status": "WARN",
            "quality": "MEDIUM",
            "fields": {"name": {"value": 'नमस्ते, "world"'}, "price": {"value": None}},
        },
        {
            "record_identity": "a",
            "validation_status": "PASS",
            "quality": "HIGH",
            "fields": {
                "name": {"value": "=SUM(A1:A2)"},
                "price": {"value": {"amount": 9, "currency": "INR"}},
            },
        },
        {
            "record_identity": "c",
            "validation_status": "FAIL",
            "quality": "INVALID",
            "fields": {"name": {"value": "Excluded"}, "price": {"value": 3}},
        },
    ]


def test_canonical_dataset_policy_order_and_immutability() -> None:
    source = records()
    dataset = build_dataset(
        plan=plan(),
        validation_run_id="run-1",
        records=source,
        options=ExportOptions(record_policy="VALID_AND_WARNINGS", include_validation_metadata=True),
        max_records=10,
    )
    assert dataset.fields == ("name", "price", "validation_status", "quality")
    assert [row["validation_status"] for row in dataset.rows] == ["PASS", "WARN"]
    assert source[0]["fields"]["price"]["value"] is None  # type: ignore[index]


def test_csv_json_and_xlsx_share_canonical_rows_and_round_trip() -> None:
    dataset = build_dataset(
        plan=plan(),
        validation_run_id="run-1",
        records=records(),
        options=ExportOptions(include_validation_metadata=True),
        max_records=10,
    )
    csv_bytes = writer_for("csv").write(dataset)
    csv_rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))))
    assert csv_rows[0]["name"] == "'=SUM(A1:A2)"
    assert csv_rows[1]["price"] == ""
    json_payload = json.loads(writer_for("json").write(dataset))
    assert json_payload["fields"] == list(dataset.fields) and json_payload["records"][1]["price"] is None
    workbook = load_workbook(io.BytesIO(writer_for("xlsx").write(dataset)))
    sheet = workbook["Data"]
    assert [cell.value for cell in sheet[1]] == list(dataset.fields)
    assert sheet["A2"].value == "'=SUM(A1:A2)" and sheet.freeze_panes == "A2"


def test_empty_dataset_is_deterministic_and_has_headers() -> None:
    dataset = build_dataset(
        plan=plan(), validation_run_id="run-empty", records=[], options=ExportOptions(), max_records=10
    )
    assert len(list(csv.DictReader(io.StringIO(writer_for("csv").write(dataset).decode())))) == 0
    assert json.loads(writer_for("json").write(dataset))["records"] == []

from __future__ import annotations

from planner_fixtures import valid_plan
from wde_api.extraction_service import ExtractionService, normalize
from wde_api.extraction_types import ContentBlockSignal, ExtractionDocument, TableSignal
from wde_api.planner_types import CanonicalPlan


def plan() -> CanonicalPlan:
    raw = valid_plan()
    raw["fields"] = [
        {"name": "name", "label": "Product", "type": "string", "required": True, "description": "Name"},
        {"name": "price", "label": "Price", "type": "currency", "required": True, "description": "Price"},
        {"name": "url", "label": "URL", "type": "url", "required": False, "description": "URL"},
    ]
    return CanonicalPlan.model_validate(raw)


def test_normalization_is_safe_and_preserves_missing_values() -> None:
    assert normalize(" $1,299.50 ", "currency", base_url="https://example.com") == 1299.5
    assert normalize("yes", "boolean", base_url="https://example.com") is True
    assert (
        normalize("item/1", "url", base_url="https://example.com/products/")
        == "https://example.com/products/item/1"
    )
    assert normalize("not-a-number", "number", base_url="https://example.com") is None
    assert normalize(None, "string", base_url="https://example.com") is None


def test_structured_data_extracts_only_requested_fields_with_evidence() -> None:
    result = ExtractionService().extract(
        plan=plan(),
        page_url="https://example.com/p/1",
        page_id="page-1",
        document=ExtractionDocument(
            json_ld=(
                """{"@type":"Product","name":"Widget","offers":{"price":"29.95"},"url":"/p/1","brand":"Ignored"}""",
            )
        ),
    )
    record = result.records[0]
    assert record.fields["name"].value == "Widget"
    assert record.fields["price"].value == 29.95
    assert record.fields["url"].value == "https://example.com/p/1"
    assert set(record.fields) == {"name", "price", "url"}
    assert record.fields["name"].evidence and record.fields["name"].evidence.source_text == "Widget"


def test_table_records_keep_row_boundaries_and_do_not_mix_neighbour_values() -> None:
    result = ExtractionService().extract(
        plan=plan(),
        page_url="https://example.com/products",
        page_id="page-2",
        document=ExtractionDocument(
            tables=(TableSignal(("Product", "Price", "Ignored"), (("A", "$10", "x"), ("B", "$20", "y"))),)
        ),
    )
    assert [(record.fields["name"].value, record.fields["price"].value) for record in result.records] == [
        ("A", 10.0),
        ("B", 20.0),
    ]


def test_repeated_blocks_keep_each_candidate_container_separate() -> None:
    result = ExtractionService().extract(
        plan=plan(),
        page_url="https://example.com/products",
        page_id="page-3",
        document=ExtractionDocument(
            blocks=(
                ContentBlockSignal("article", "A $10", "/a"),
                ContentBlockSignal("article", "B $20", "/b"),
            )
        ),
    )
    assert len(result.records) == 2
    assert [record.fields["url"].value for record in result.records] == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_detail_record_explicitly_represents_missing_fields_without_validation_status() -> None:
    result = ExtractionService().extract(
        plan=plan(),
        page_url="https://example.com/p/4",
        page_id="page-4",
        document=ExtractionDocument(page_text="A short page"),
    )
    record = result.records[0]
    assert record.fields["price"].value is None and record.fields["price"].missing
    assert "validation_status" not in record.provenance and "quality_score" not in record.provenance

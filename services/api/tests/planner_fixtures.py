from __future__ import annotations


def valid_plan(
    *,
    source_url: str = "https://example.com/products",
    max_pages: int = 20,
    max_records: int = 1000,
    outputs: list[str] | None = None,
    fields: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "plan.v1",
        "plan_version": 1,
        "source": {"url": source_url, "scope": "site"},
        "intent": {"summary": "Collect structured product records.", "objective": "structured_records"},
        "fields": fields
        if fields is not None
        else [
            {
                "name": "name",
                "label": "Product name",
                "type": "string",
                "required": True,
                "description": "The displayed product name.",
                "aliases": ["title"],
                "example_value": "Sample product",
                "normalization_hint": "Trim surrounding whitespace.",
            },
            {
                "name": "price",
                "label": "Price",
                "type": "currency",
                "required": False,
                "description": "The displayed product price.",
                "aliases": [],
                "example_value": "$12.00",
                "normalization_hint": "Preserve the displayed currency symbol.",
            },
        ],
        "navigation": {
            "follow_pagination": True,
            "pagination_likely": True,
            "follow_relevant_links": False,
            "relevant_link_purpose": None,
            "max_pages": max_pages,
        },
        "deduplication": {"enabled": True, "keys": ["name"]},
        "validation": {
            "enabled": True,
            "expectations": [{"field": "name", "rule": "must not be blank"}],
        },
        "limits": {"max_pages": max_pages, "max_records": max_records},
        "outputs": outputs or ["json"],
        "assumptions": [
            {"statement": "Product records are represented consistently.", "confidence": "medium"}
        ],
        "ambiguities": [],
    }


def options() -> dict[str, object]:
    return {
        "max_pages": 20,
        "max_records": 1000,
        "follow_pagination": True,
        "follow_relevant_links": False,
        "extract_images": False,
        "deduplicate": True,
        "validate": True,
    }

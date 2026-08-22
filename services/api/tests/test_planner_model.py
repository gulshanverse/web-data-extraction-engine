from __future__ import annotations

import asyncio

import httpx
import pytest
from wde_api.config import Settings
from wde_api.planner_errors import (
    PlannerInvalidOutput,
    PlannerNotConfigured,
    PlannerRateLimited,
    PlannerTimeout,
)
from wde_api.planner_model import OpenAICompatiblePlannerModel, build_planner_model, strict_json_schema
from wde_api.planner_types import CanonicalPlan


def test_factory_never_falls_back_to_fake_model_when_configuration_is_missing() -> None:
    model = build_planner_model(Settings(planner_api_endpoint="", planner_api_key=""))
    with pytest.raises(PlannerNotConfigured):
        asyncio.run(model.generate_plan(user_request="task", schema={}, context={}))


def test_strict_schema_sets_closed_objects_and_required_properties_recursively() -> None:
    schema = strict_json_schema(CanonicalPlan.model_json_schema())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    field = schema["$defs"]["PlanField"]
    assert field["additionalProperties"] is False
    assert set(field["required"]) == set(field["properties"])


@pytest.mark.asyncio
async def test_provider_classifies_rate_limit_and_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            self.response = httpx.Response(429)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, *args, **kwargs):
            return self.response

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    model = OpenAICompatiblePlannerModel(
        endpoint="https://provider.example/v1",
        api_key="redacted",
        model_name="test",
        timeout_seconds=1,
        max_tokens=256,
    )
    with pytest.raises(PlannerRateLimited):
        await model.generate_plan(user_request="task", schema={}, context={})

    class InvalidJsonClient(FakeClient):
        def __init__(self, *args, **kwargs) -> None:
            self.response = httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    monkeypatch.setattr(httpx, "AsyncClient", InvalidJsonClient)
    with pytest.raises(PlannerInvalidOutput):
        await model.generate_plan(user_request="task", schema={}, context={})


@pytest.mark.asyncio
async def test_provider_classifies_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class TimeoutClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(httpx, "AsyncClient", TimeoutClient)
    model = OpenAICompatiblePlannerModel(
        endpoint="https://provider.example/v1",
        api_key="redacted",
        model_name="test",
        timeout_seconds=1,
        max_tokens=256,
    )
    with pytest.raises(PlannerTimeout):
        await model.generate_plan(user_request="task", schema={}, context={})

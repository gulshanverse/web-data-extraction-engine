"""Provider boundary for Phase 4; models receive text and return declarative JSON only."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from wde_api.config import Settings
from wde_api.planner_errors import (
    PlannerInvalidOutput,
    PlannerNotConfigured,
    PlannerRateLimited,
    PlannerTimeout,
    PlannerUnavailable,
)


class PlannerModel(Protocol):
    provider_name: str
    model_name: str

    async def generate_plan(
        self, *, user_request: str, schema: dict[str, object], context: dict[str, object]
    ) -> object: ...


def strict_json_schema(schema: dict[str, object]) -> dict[str, object]:
    """Normalize generated Pydantic schema for strict OpenAI-compatible responses."""
    normalized = copy.deepcopy(schema)

    def visit(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = sorted(properties)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(normalized)
    return normalized


class OpenAICompatiblePlannerModel:
    """Configured production provider. It performs no target-website I/O."""

    provider_name = "openai_compatible"

    def __init__(
        self, *, endpoint: str, api_key: str, model_name: str, timeout_seconds: float, max_tokens: int
    ) -> None:
        self.endpoint, self.api_key, self.model_name = endpoint.rstrip("/"), api_key, model_name
        self.timeout_seconds, self.max_tokens = timeout_seconds, max_tokens
        self.system_prompt = (Path(__file__).parent / "prompts/planner/system_v1.txt").read_text(
            encoding="utf-8"
        )

    async def generate_plan(
        self, *, user_request: str, schema: dict[str, object], context: dict[str, object]
    ) -> object:
        body = {
            "model": self.model_name,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps({"request": user_request, "context": context})},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "canonical_plan",
                    "strict": True,
                    "schema": strict_json_schema(schema),
                },
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.endpoint}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise PlannerTimeout("Planner provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise PlannerUnavailable("Planner provider is unavailable.") from exc
        if response.status_code == 429:
            raise PlannerRateLimited("Planner provider rate limited the request.")
        if response.status_code >= 500:
            raise PlannerUnavailable("Planner provider is unavailable.")
        if response.status_code in {400, 401, 403, 404}:
            raise PlannerNotConfigured("Planner provider configuration is unavailable.")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Planner response content is not text.")
            return json.loads(content)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PlannerInvalidOutput("Planner provider did not return valid JSON.") from exc


class UnavailablePlannerModel:
    """Terminal configuration guard used when a production provider is not usable."""

    provider_name = "unconfigured"
    model_name = "unconfigured"

    def __init__(self, message: str) -> None:
        self.message = message

    async def generate_plan(
        self, *, user_request: str, schema: dict[str, object], context: dict[str, object]
    ) -> object:
        raise PlannerNotConfigured(self.message)


def build_planner_model(settings: Settings) -> PlannerModel:
    """Build only a configured production provider; never fall back to deterministic output."""
    endpoint = settings.planner_api_endpoint.strip()
    api_key = settings.planner_api_key.strip()
    if settings.planner_provider != "openai_compatible":
        return UnavailablePlannerModel("Planner provider is not configured.")
    parsed = urlparse(endpoint)
    if not endpoint or parsed.scheme not in {"http", "https"} or not parsed.netloc or not api_key:
        return UnavailablePlannerModel("Planner provider is not configured.")
    return OpenAICompatiblePlannerModel(
        endpoint=endpoint,
        api_key=api_key,
        model_name=settings.planner_model,
        timeout_seconds=settings.planner_timeout_seconds,
        max_tokens=settings.planner_max_output_tokens,
    )


class DeterministicPlannerModel:
    """Explicit test double; never selected by production settings."""

    provider_name = "deterministic_test"
    model_name = "deterministic-test-v1"

    def __init__(self, output: object | Exception) -> None:
        self.output = output

    async def generate_plan(
        self, *, user_request: str, schema: dict[str, object], context: dict[str, object]
    ) -> object:
        if isinstance(self.output, Exception):
            raise self.output
        await asyncio.sleep(0)
        return self.output

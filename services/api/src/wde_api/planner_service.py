"""Phase 4 planning domain service; it never accesses target websites or browser infrastructure."""

from __future__ import annotations

import re

from wde_api.config import Settings
from wde_api.planner_errors import PlannerPolicyRejected
from wde_api.planner_model import PlannerModel
from wde_api.planner_types import CanonicalPlan, validate_plan

_INJECTION = re.compile(
    r"(?:ignore|disregard|override)\s+(?:all\s+|previous\s+|prior\s+)?instructions?|"
    r"reveal\s+(?:the\s+)?(?:system\s+)?prompt|"
    r"(?:api|access)[ _-]?key|"
    r"bypass\s+(?:a\s+|the\s+)?(?:policy|guardrail|restriction)|"
    r"(?:run|execute)\s+(?:a\s+)?(?:shell|sql|python|javascript)\s+(?:command|code)",
    re.I,
)


class PlannerService:
    def __init__(self, model: PlannerModel, settings: Settings) -> None:
        self.model = model
        self.settings = settings

    def normalize_request(self, task: str) -> str:
        normalized = " ".join(task.split())
        if not normalized or len(normalized) > self.settings.planner_max_task_chars:
            raise PlannerPolicyRejected("The requested planning task is empty or exceeds the allowed length.")
        if _INJECTION.search(normalized):
            raise PlannerPolicyRejected("The requested planning task contains unsafe instructions.")
        return normalized

    async def create_plan(
        self,
        *,
        source_url: str,
        task: str,
        requested_fields: list[str],
        options: dict[str, object],
        outputs: list[str],
    ) -> CanonicalPlan:
        request = self.normalize_request(task)
        raw = await self.model.generate_plan(
            user_request=request,
            schema=CanonicalPlan.model_json_schema(),
            context={
                "source_url": source_url,
                "requested_fields": requested_fields,
                "explicit_options": options,
                "requested_outputs": outputs,
                "server_limits": {
                    "max_pages": self.settings.planner_max_pages,
                    "max_records": self.settings.planner_max_records,
                    "max_fields": self.settings.planner_max_fields,
                    "max_outputs": self.settings.planner_max_outputs,
                },
            },
        )
        return validate_plan(
            raw,
            source_url=source_url,
            max_pages=self.settings.planner_max_pages,
            max_records=self.settings.planner_max_records,
            max_fields=self.settings.planner_max_fields,
            max_outputs=self.settings.planner_max_outputs,
            requested_options=options,
            requested_outputs=outputs,
        )

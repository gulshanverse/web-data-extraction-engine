"""Typed FastAPI contracts matching the Phase 0 public API without accepting arbitrary dictionaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wde_api.url_policy import validate_initial_url

SUPPORTED_OUTPUT_FORMATS = {"xlsx", "csv", "json", "pdf", "docx", "md", "txt"}


class JobOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    max_pages: int = Field(default=20, ge=1, le=100)
    max_records: int = Field(default=1000, ge=1, le=10000)
    follow_pagination: bool = True
    follow_relevant_links: bool = False
    extract_images: bool = False
    deduplicate: bool = True
    validate_results: bool = Field(default=True, alias="validate", serialization_alias="validate")


class JobCreateRequest(BaseModel):
    project_id: UUID
    source_url: str = Field(min_length=8, max_length=2048)
    task: str = Field(min_length=16, max_length=10_000)
    fields: list[str] = Field(min_length=1, max_length=100)
    options: JobOptions = Field(default_factory=JobOptions)
    output_formats: list[str] = Field(min_length=1, max_length=7)

    @field_validator("source_url")
    @classmethod
    def source_url_is_permitted(cls, value: str) -> str:
        return validate_initial_url(value).canonical_url

    @field_validator("fields")
    @classmethod
    def unique_fields(cls, fields: list[str]) -> list[str]:
        cleaned = [field.strip() for field in fields if field.strip()]
        if len(cleaned) != len(fields) or len(set(cleaned)) != len(cleaned):
            raise ValueError("Fields must be non-empty and unique.")
        return cleaned

    @field_validator("output_formats")
    @classmethod
    def output_formats_supported(cls, formats: list[str]) -> list[str]:
        normalized = [value.lower().lstrip(".") for value in formats]
        unsupported = set(normalized) - SUPPORTED_OUTPUT_FORMATS
        if unsupported:
            raise ValueError(f"Unsupported output format: {sorted(unsupported)[0]}")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Output formats must be unique.")
        return normalized


class ProgressProjection(BaseModel):
    percent: int = Field(ge=0, le=100)
    stage: str
    message: str | None = None
    pages_discovered: int = 0
    pages_processed: int = 0
    records_found: int = 0
    records_valid: int = 0
    updated_at: datetime | None = None


class JobAccepted(BaseModel):
    job_id: UUID
    project_id: UUID
    status: str
    progress: ProgressProjection
    created_at: datetime


class PlanProjection(BaseModel):
    version: int
    status: str


class ErrorProjection(BaseModel):
    code: str
    message: str
    retryable: bool
    correlation_id: UUID


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    progress: ProgressProjection
    plan: PlanProjection | None = None
    error: ErrorProjection | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class CancelResponse(BaseModel):
    job_id: UUID
    status: str
    cancelled_at: datetime | None


class ResultsResponse(BaseModel):
    job_id: UUID
    plan_version: int | None = None
    schema_version: str = "records.v1"
    items: list[dict[str, Any]] = Field(default_factory=list)
    page: int = 1
    page_size: int = 100
    total: int = 0
    validation_summary: dict[str, int] = Field(
        default_factory=lambda: {"passed": 0, "warnings": 0, "failed": 0}
    )


class FileMetadata(BaseModel):
    file_id: UUID
    format: str
    media_type: str
    byte_size: int
    checksum: str
    download_url: str | None = None
    expires_at: datetime | None = None


class FilesResponse(BaseModel):
    job_id: UUID
    files: list[FileMetadata] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool
    correlation_id: UUID
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorBody

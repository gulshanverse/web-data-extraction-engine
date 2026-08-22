import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from planner_fixtures import options, valid_plan
from sqlalchemy import func, select
from wde_api.config import get_settings
from wde_api.database import SessionFactory
from wde_api.export_errors import ExportSerializationError, ExportTooLarge
from wde_api.export_service import render_export, writer_for
from wde_api.main import app
from wde_api.models import (
    ExportJob,
    ExtractionJob,
    ExtractionPlan,
    GeneratedFile,
    Record,
    User,
    ValidationRun,
    WorkOutbox,
)
from wde_api.schemas import JobCreateRequest
from wde_api.services import JobService
from wde_api.storage import ArtifactRef, LocalArtifactStore
from wde_api.worker import run_export

PROJECT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
FORMATS = ("xlsx", "csv", "json", "pdf", "docx", "md", "txt", "html")


def plan_outputs(formats: list[str]) -> list[str]:
    return [{"xlsx": "excel", "md": "markdown"}.get(format_name, format_name) for format_name in formats]


async def export_ready(formats: list[str]) -> tuple[JobService, list[dict[str, object]]]:
    service = JobService()
    async with SessionFactory() as session:
        async with session.begin():
            principal = await session.scalar(select(User).where(User.email == "developer@example.invalid"))
            accepted = await service.create_job(
                session,
                JobCreateRequest.model_validate(
                    {
                        "project_id": str(PROJECT_ID),
                        "source_url": "https://example.com/products",
                        "task": "Extract product names and prices from the catalog.",
                        "fields": ["name", "price"],
                        "options": options(),
                        "output_formats": formats,
                    }
                ),
                principal_id=principal.id,
                idempotency_key=f"export-{uuid.uuid4()}",
                correlation_id=uuid.uuid4(),
            )
            job = await session.get(ExtractionJob, accepted.job_id)
            job.status = "VALIDATING"
            session.add(
                ExtractionPlan(
                    job_id=job.id,
                    version=1,
                    status="ACTIVE",
                    plan=valid_plan(outputs=plan_outputs(formats)),
                )
            )
            session.add(
                Record(
                    job_id=job.id,
                    payload={
                        "schema_version": "records.v1",
                        "fields": {
                            "name": {
                                "raw": "Widget",
                                "value": "Widget",
                                "evidence": {"source_text": "Widget", "location": "table[0]"},
                            },
                            "price": {
                                "raw": "$12.00",
                                "value": "$12.00",
                                "evidence": {"source_text": "$12.00", "location": "table[0]"},
                            },
                        },
                    },
                    record_identity="record-1",
                    plan_version=1,
                    provenance={"canonical_url": "https://example.com/products"},
                )
            )
            run = ValidationRun(
                job_id=job.id,
                run_number=1,
                operation_key=f"job:{job.id}:validation:run:1",
                status="QUEUED",
                schema_version="validation.v1",
                ruleset_version="rules.v1",
                plan_version=1,
            )
            session.add(run)
            await session.flush()
            command = {
                "job_id": str(job.id),
                "project_id": str(job.project_id),
                "correlation_id": str(job.correlation_id),
                "operation_key": run.operation_key,
                "validation_run_id": str(run.id),
                "attempt": 1,
            }
            operation = await service.claim_validation(session, command, worker_id="test", lease_seconds=120)
            from wde_api.validation_service import ValidationService

            await service.complete_validation_run(session, operation, ValidationService())
            commands = list(
                await session.scalars(
                    select(WorkOutbox.payload)
                    .where(WorkOutbox.job_id == job.id, WorkOutbox.command_type == "run_export")
                    .order_by(WorkOutbox.created_at)
                )
            )
    return service, commands


async def complete_command(
    service: JobService, command: dict[str, object], store: LocalArtifactStore
) -> None:
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_export(session, command, worker_id="test", lease_seconds=120)
    assert operation is not None
    async with SessionFactory() as session:
        dataset = await service.load_export_dataset(session, operation, max_records=10_000)
        assert not await service.export_cancelled(session, operation)
    writer = writer_for(operation.format_name)
    data = render_export(dataset, operation.format_name)

    async def stream():
        yield data

    ref = await store.put("generated_export", stream(), media_type=writer.media_type, metadata={})
    async with SessionFactory() as session:
        async with session.begin():
            assert await service.complete_export(
                session,
                operation,
                storage_key=ref.key,
                media_type=ref.media_type,
                byte_size=ref.byte_size,
                checksum=ref.checksum,
                expires_at=ref.expires_at,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("format_name", FORMATS)
async def test_every_registered_format_completes_durable_storage_and_file_lifecycle(
    format_name: str, tmp_path
) -> None:
    service, commands = await export_ready([format_name])
    assert len(commands) == 1
    store = LocalArtifactStore(tmp_path, max_bytes=25_165_824)
    await complete_command(service, commands[0], store)
    job_id = uuid.UUID(str(commands[0]["job_id"]))
    async with SessionFactory() as session:
        principal = await session.scalar(select(User).where(User.email == "developer@example.invalid"))
        files = await service.files(session, job_id=job_id, principal_id=principal.id)
        export = await session.scalar(select(ExportJob).where(ExportJob.job_id == job_id))
        job = await session.get(ExtractionJob, job_id)
    assert export.status == "COMPLETED" and job.status == "COMPLETED"
    assert len(files.files) == 1
    metadata = files.files[0]
    assert metadata.format == format_name and metadata.filename.endswith(f".{format_name}")
    assert metadata.download_url == f"/api/files/{metadata.file_id}/download"
    assert metadata.byte_size > 0 and metadata.media_type == writer_for(format_name).media_type


@pytest.mark.asyncio
async def test_duplicate_export_delivery_reuses_one_export_and_generated_file(tmp_path) -> None:
    service, commands = await export_ready(["json"])
    store = LocalArtifactStore(tmp_path)
    await complete_command(service, commands[0], store)
    async with SessionFactory() as session:
        async with session.begin():
            assert (
                await service.claim_export(session, commands[0], worker_id="test", lease_seconds=120) is None
            )
        export_count = await session.scalar(select(func.count()).select_from(ExportJob))
        file_count = await session.scalar(select(func.count()).select_from(GeneratedFile))
    assert export_count == file_count == 1


@pytest.mark.asyncio
async def test_export_worker_handles_durable_outbox_command_end_to_end(tmp_path) -> None:
    service, commands = await export_ready(["pdf"])
    await run_export(
        {"export_capacity": asyncio.Semaphore(1), "export_store": LocalArtifactStore(tmp_path)},
        commands[0],
    )
    job_id = uuid.UUID(str(commands[0]["job_id"]))
    async with SessionFactory() as session:
        job = await session.get(ExtractionJob, job_id)
        export = await session.get(ExportJob, uuid.UUID(str(commands[0]["export_job_id"])))
        file = await session.scalar(select(GeneratedFile).where(GeneratedFile.export_job_id == export.id))
    assert job.status == "COMPLETED" and export.status == "COMPLETED"
    assert file is not None and file.media_type == "application/pdf" and file.filename.endswith(".pdf")


@pytest.mark.asyncio
async def test_export_cancellation_and_terminal_failure_are_durable(tmp_path) -> None:
    service, commands = await export_ready(["json"])
    command = commands[0]
    async with SessionFactory() as session:
        async with session.begin():
            job = await session.get(ExtractionJob, uuid.UUID(str(command["job_id"])))
            job.cancel_requested_at = datetime.now(UTC)
            assert await service.claim_export(session, command, worker_id="test", lease_seconds=120) is None
        export = await session.get(ExportJob, uuid.UUID(str(command["export_job_id"])))
    assert export.status == "CANCELLED"

    service, commands = await export_ready(["json"])
    async with SessionFactory() as session:
        async with session.begin():
            retry = await service.fail_export(
                session, commands[0], ExportSerializationError("bad data"), max_attempts=2
            )
        export = await session.get(ExportJob, uuid.UUID(str(commands[0]["export_job_id"])))
        job = await session.get(ExtractionJob, uuid.UUID(str(commands[0]["job_id"])))
    assert retry is None and export.status == "FAILED" and job.status == "FAILED"


@pytest.mark.asyncio
async def test_expired_export_lease_requeues_the_existing_export_operation() -> None:
    service, commands = await export_ready(["json"])
    command = commands[0]
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_export(session, command, worker_id="test", lease_seconds=120)
            job = await session.get(ExtractionJob, operation.job_id)
            job.lease_expires_at = datetime(2000, 1, 1, tzinfo=UTC)
        async with session.begin():
            assert await service.recover_expired_leases(session) == 1
        export = await session.get(ExportJob, operation.export_job_id)
        requeued = await session.scalar(
            select(WorkOutbox)
            .where(
                WorkOutbox.command_type == "run_export", WorkOutbox.operation_key != command["operation_key"]
            )
            .order_by(WorkOutbox.created_at.desc())
            .limit(1)
        )
    assert export.status == "QUEUED"
    assert requeued is not None and requeued.payload["export_job_id"] == str(operation.export_job_id)


@pytest.mark.asyncio
async def test_export_dataset_limit_and_file_authorization_are_enforced(tmp_path) -> None:
    service, commands = await export_ready(["csv"])
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_export(session, commands[0], worker_id="test", lease_seconds=120)
        with pytest.raises(ExportTooLarge):
            await service.load_export_dataset(session, operation, max_records=0)
        await service.fail_export(session, commands[0], ExportTooLarge("bounded"), max_attempts=2)
        await session.commit()
    service, commands = await export_ready(["csv"])
    await complete_command(service, commands[0], LocalArtifactStore(tmp_path))
    async with SessionFactory() as session:
        file = await session.scalar(select(GeneratedFile))
        other = User(email="other@example.invalid")
        session.add(other)
        await session.commit()
        with pytest.raises(Exception) as denied:
            await service.file_for_download(session, file_id=file.id, principal_id=other.id)
    assert getattr(denied.value, "code", None) == "NOT_FOUND"


@pytest.mark.asyncio
async def test_files_api_lists_and_downloads_only_authorized_artifacts() -> None:
    service, commands = await export_ready(["txt"])
    store = LocalArtifactStore(get_settings().artifact_root, max_bytes=25_165_824)
    await complete_command(service, commands[0], store)
    job_id = commands[0]["job_id"]
    async with SessionFactory() as session:
        file = await session.scalar(select(GeneratedFile))
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            listed = client.get(f"/api/jobs/{job_id}/files")
            assert listed.status_code == 200
            metadata = listed.json()["files"][0]
            assert metadata["filename"].endswith(".txt") and "storage_key" not in metadata
            downloaded = client.get(metadata["download_url"])
            assert downloaded.status_code == 200 and downloaded.headers["content-type"].startswith(
                "text/plain"
            )
            denied = client.get(
                metadata["download_url"], headers={"X-Dev-Principal": "other@example.invalid"}
            )
            assert denied.status_code == 404 and denied.json()["error"]["code"] == "NOT_FOUND"
    finally:
        await store.delete(
            ArtifactRef(
                key=file.storage_key,
                artifact_type="generated_export",
                media_type=file.media_type,
                byte_size=file.byte_size,
                checksum=file.checksum,
                created_at=file.created_at,
                expires_at=file.expires_at,
            )
        )


def test_document_and_tabular_media_types_are_explicitly_allowed(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    assert writer_for("xlsx").media_type in store.allowed_media_types
    assert writer_for("pdf").media_type in store.allowed_media_types
    assert writer_for("docx").media_type in store.allowed_media_types
    assert writer_for("md").media_type in store.allowed_media_types
    assert writer_for("txt").media_type in store.allowed_media_types
    assert writer_for("html").media_type in store.allowed_media_types

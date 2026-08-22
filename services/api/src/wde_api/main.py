"""Phase 2 FastAPI application exposing durable job-orchestration contracts only."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from wde_api.auth import resolve_development_principal
from wde_api.config import get_settings
from wde_api.database import SessionFactory, dependency_ready, get_session
from wde_api.domain import DomainError, JobStatus
from wde_api.logging import configure_logging
from wde_api.models import ExtractionJob
from wde_api.queue import OutboxDispatcher, redis_ready
from wde_api.schemas import (
    CancelResponse,
    ErrorEnvelope,
    FilesResponse,
    JobAccepted,
    JobCreateRequest,
    JobStatusResponse,
    PageInventoryResponse,
    ResultsResponse,
)
from wde_api.security import SlidingWindowRateLimiter
from wde_api.services import JobService
from wde_api.storage import ArtifactRef, LocalArtifactStore

service, dispatcher = JobService(), OutboxDispatcher()
log = structlog.get_logger()
settings = get_settings()
rate_limiter = SlidingWindowRateLimiter(
    settings.api_rate_limit_requests, settings.api_rate_limit_window_seconds
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    yield


app = FastAPI(title="Web Data Extraction Engine API", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    raw = request.headers.get("X-Correlation-ID")
    try:
        correlation_id = uuid.UUID(raw) if raw else uuid.uuid4()
    except ValueError:
        correlation_id = uuid.uuid4()
    request.state.correlation_id = correlation_id
    if request.url.path.startswith("/api/"):
        client_key = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_key):
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "The request rate limit was reached.",
                        "retryable": True,
                        "correlation_id": str(correlation_id),
                        "details": {},
                    }
                },
                headers={
                    "Retry-After": str(max(1, int(settings.api_rate_limit_window_seconds))),
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                    "Cache-Control": "no-store",
                },
            )
        if request.method in {"POST", "PUT", "PATCH"}:
            declared_size = request.headers.get("content-length")
            if declared_size and declared_size.isdigit() and int(declared_size) > settings.max_request_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "RESOURCE_LIMIT_EXCEEDED",
                            "message": "The request exceeds the configured size limit.",
                            "retryable": False,
                            "correlation_id": str(correlation_id),
                            "details": {},
                        }
                    },
                    headers={
                        "X-Content-Type-Options": "nosniff",
                        "X-Frame-Options": "DENY",
                        "Referrer-Policy": "no-referrer",
                        "Cache-Control": "no-store",
                    },
                )
            if len(await request.body()) > settings.max_request_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "RESOURCE_LIMIT_EXCEEDED",
                            "message": "The request exceeds the configured size limit.",
                            "retryable": False,
                            "correlation_id": str(correlation_id),
                            "details": {},
                        }
                    },
                    headers={
                        "X-Content-Type-Options": "nosniff",
                        "X-Frame-Options": "DENY",
                        "Referrer-Policy": "no-referrer",
                        "Cache-Control": "no-store",
                    },
                )
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = str(correlation_id)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Cache-Control", "no-store" if request.url.path.startswith("/api/") else "no-cache"
    )
    return response


def correlation(request: Request) -> uuid.UUID:
    return request.state.correlation_id


async def development_principal(request: Request, session: AsyncSession):
    return await resolve_development_principal(session, request.headers.get("X-Dev-Principal"))


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    body = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
            "correlation_id": str(correlation(request)),
            "details": exc.details,
        }
    }
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    messages = " ".join(str(item.get("msg", "")) for item in exc.errors()).lower()
    code = "INVALID_REQUEST"
    if "unsupported output format" in messages:
        code = "UNSUPPORTED_FORMAT"
    elif "less than or equal" in messages or "greater than or equal" in messages:
        code = "RESOURCE_LIMIT_EXCEEDED"
    body = {
        "error": {
            "code": code,
            "message": "The request does not match the required contract.",
            "retryable": False,
            "correlation_id": str(correlation(request)),
            "details": {"fields": [item["loc"][-1] for item in exc.errors()]},
        }
    }
    return JSONResponse(status_code=422, content=body)


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", correlation_id=str(correlation(request)), error_type=type(exc).__name__)
    body = {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "The request could not be completed safely.",
            "retryable": False,
            "correlation_id": str(correlation(request)),
            "details": {},
        }
    }
    return JSONResponse(status_code=500, content=body)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def readiness() -> JSONResponse:
    database_ok, redis_ok = await dependency_ready(), await redis_ready()
    status = 200 if database_ok and redis_ok else 503
    return JSONResponse(
        status_code=status,
        content={
            "status": "ready" if status == 200 else "unavailable",
            "database": database_ok,
            "redis": redis_ok,
        },
    )


@app.post(
    "/api/jobs",
    status_code=202,
    response_model=JobAccepted,
    responses={
        400: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def create_job(
    command: JobCreateRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> JobAccepted:
    principal = await development_principal(request, session)
    result = await service.create_job(
        session,
        command,
        principal_id=principal.id,
        idempotency_key=idempotency_key,
        correlation_id=correlation(request),
    )
    await session.commit()
    try:
        async with session.begin():
            await dispatcher.dispatch_pending(session)
    except Exception:
        log.warning(
            "outbox_publish_deferred", job_id=str(result.job_id), correlation_id=str(correlation(request))
        )
    return result


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse, responses={404: {"model": ErrorEnvelope}})
async def job_status(
    job_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> JobStatusResponse:
    principal = await development_principal(request, session)
    return await service.status(session, job_id=job_id, principal_id=principal.id)


@app.post(
    "/api/jobs/{job_id}/cancel",
    status_code=202,
    response_model=CancelResponse,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def cancel_job(
    job_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> CancelResponse:
    principal = await development_principal(request, session)
    response = await service.cancel(
        session, job_id=job_id, principal_id=principal.id, correlation_id=correlation(request)
    )
    await session.commit()
    return response


@app.get("/api/jobs/{job_id}/results", response_model=ResultsResponse)
async def job_results(
    job_id: uuid.UUID,
    request: Request,
    page: int = 1,
    page_size: int = 100,
    session: AsyncSession = Depends(get_session),
) -> ResultsResponse:
    principal = await development_principal(request, session)
    return await service.results(
        session,
        job_id=job_id,
        principal_id=principal.id,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
    )


@app.get("/api/jobs/{job_id}/files", response_model=FilesResponse)
async def job_files(
    job_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> FilesResponse:
    principal = await development_principal(request, session)
    return await service.files(session, job_id=job_id, principal_id=principal.id)


@app.get("/api/files/{file_id}/download", responses={404: {"model": ErrorEnvelope}})
async def download_file(
    file_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> StreamingResponse:
    """Stream one authorized generated artifact; storage keys stay internal to the server."""
    principal = await development_principal(request, session)
    file, _ = await service.file_for_download(session, file_id=file_id, principal_id=principal.id)
    reference = ArtifactRef(
        key=file.storage_key,
        artifact_type="generated_export",
        media_type=file.media_type,
        byte_size=file.byte_size,
        checksum=file.checksum,
        created_at=file.created_at,
        expires_at=file.expires_at,
    )
    store = LocalArtifactStore(get_settings().artifact_root, max_bytes=get_settings().export_max_bytes)
    return StreamingResponse(
        store.open(reference),
        media_type=file.media_type,
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
    )


@app.get("/api/jobs/{job_id}/pages", response_model=PageInventoryResponse)
async def job_pages(
    job_id: uuid.UUID,
    request: Request,
    page: int = 1,
    page_size: int = 100,
    session: AsyncSession = Depends(get_session),
) -> PageInventoryResponse:
    principal = await development_principal(request, session)
    return await service.pages(
        session,
        job_id=job_id,
        principal_id=principal.id,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
    )


@app.get("/api/jobs/{job_id}/events")
async def job_events(
    job_id: uuid.UUID,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    principal = await development_principal(request, session)
    await service.get_job(session, job_id, principal.id)
    after = int(last_event_id or "0") if (last_event_id or "0").isdigit() else 0

    async def event_stream() -> AsyncIterator[str]:
        cursor = after
        while not await request.is_disconnected():
            async with SessionFactory() as scoped:
                events = await service.events_after(scoped, job_id=job_id, after_sequence=cursor)
                job = await scoped.get(ExtractionJob, job_id)
            for event in events:
                cursor = event.sequence_no
                yield f"id: {event.sequence_no}\nevent: {event.event_type}\ndata: {json.dumps({'job_id': str(event.job_id), **event.payload, 'occurred_at': event.occurred_at.isoformat()})}\n\n"
            if job and job.status in {
                state.value for state in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
            }:
                break
            await asyncio.sleep(get_settings().api_event_poll_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

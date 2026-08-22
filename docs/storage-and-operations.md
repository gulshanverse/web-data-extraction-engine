# Storage Architecture and Operations

## Storage boundary

The platform separates domain processing from artifact storage. Extraction, validation, and export modules use typed storage ports; they do not construct filesystem paths, import an S3 SDK, or make assumptions about deployment topology. The adapter returns immutable references that can be persisted in PostgreSQL and authorized through the API.

## Artifact classes

| Artifact | Contents | Default location | Retention and access |
|---|---|---|---|
| Raw page snapshot | Sanitized HTML/DOM snapshot and capture metadata | Local filesystem in development; S3-compatible store later | Job/project retention; internal or authorized diagnostic access |
| Structured records | Large result payloads or batch materialization | PostgreSQL for queryable data; object storage for large batches | Authorized project access; retention policy applies |
| Generated export | CSV, JSON, XLSX, PDF, DOCX, Markdown, or TXT bytes | Storage adapter | Short-lived download link and explicit expiration |
| Temporary file | Intermediate browser, parser, or exporter data | Isolated worker temporary directory | Deleted on checkpoint, cancellation, or expiry |

## Port interface

The future implementation should expose operations similar to:

```python
class ArtifactStore(Protocol):
    async def put(
        self,
        artifact_type: ArtifactType,
        stream: AsyncIterator[bytes],
        *,
        media_type: str,
        metadata: Mapping[str, str],
        expires_at: datetime | None = None,
    ) -> ArtifactRef: ...

    async def open(self, ref: ArtifactRef) -> AsyncIterator[bytes]: ...
    async def head(self, ref: ArtifactRef) -> ArtifactMetadata: ...
    async def delete(self, ref: ArtifactRef) -> None: ...
    async def create_download_url(self, ref: ArtifactRef, *, expires_in: timedelta) -> str: ...
```

`ArtifactRef` includes an opaque key, artifact type, media type, byte size, checksum, creation timestamp, and optional expiry. The interface enforces maximum size, allowed media type, checksum calculation, and cancellation-aware streaming. It never exposes provider credentials to callers.

## Implementations

The local development adapter writes beneath a configured application data root that is not the repository source tree. It uses safe generated keys, atomic temporary-write-and-rename semantics, restrictive permissions, and cleanup on failure. Tests use an isolated temporary directory.

The later S3-compatible adapter maps artifact keys to a bucket and prefix, uses server-side encryption where available, and generates short-lived signed download URLs. Bucket names, endpoints, credentials, and lifecycle rules are deployment configuration. The rest of the platform sees only the port.

## PostgreSQL versus object storage

PostgreSQL stores metadata that must be queried or joined: artifact owner, job, export format, media type, checksum, byte size, retention, and status. It also stores normal-sized structured records and validation findings. Raw HTML, screenshots, large record batches, and generated files use object storage. A database row is created before or atomically with the durable reference; an incomplete upload is never presented as a completed file.

## Consistency and cleanup

Uploads use a pending/completed marker or an equivalent transaction/outbox workflow. An export becomes downloadable only after the bytes are fully written, checksum and size are recorded, and the metadata transaction commits. Failed or abandoned uploads are cleaned by a reconciler after a grace period.

Cleanup is ownership- and reference-aware. Expired temporary files and generated files are removed only when no active job or legal retention rule requires them. Deletion events are logged with job and artifact identifiers but not sensitive contents. A later retention service may support project-level policies and user-initiated deletion.

## Security and privacy

Storage keys are opaque and non-guessable. API authorization is checked before returning metadata or a download URL. Download links are short-lived and scoped. Sensitive output is encrypted in transit and at rest where supported. Artifact metadata and logs omit credentials, cookies, raw authorization headers, and unbounded page content.

## Testing requirements

The storage contract requires adapter conformance tests for round-trip bytes, checksum and size, expiration, cancellation, partial-write cleanup, authorization integration, invalid media types, size limits, and idempotent deletion. Local and S3-compatible adapters must pass the same contract suite.

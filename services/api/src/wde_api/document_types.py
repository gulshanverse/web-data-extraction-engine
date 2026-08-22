"""Phase 10 versioned human-readable document contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from wde_api.export_types import CanonicalExportDataset

DocumentFormat = Literal["pdf", "docx", "md", "txt", "html"]
DOCUMENT_PROFILE_VERSION = "document.v1"


@dataclass(frozen=True)
class DocumentProfile:
    title: str = "Web Data Extraction Results"
    include_validation: bool = False
    include_provenance: bool = False
    null_text: str = "—"


@dataclass(frozen=True)
class CanonicalDocument:
    profile: DocumentProfile
    dataset: CanonicalExportDataset
    metadata: dict[str, Any]

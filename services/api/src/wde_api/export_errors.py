"""Stable Phase 8 export errors."""


class ExportError(Exception):
    code = "EXPORT_FAILED"
    retryable = False

    def __init__(self, message: str = "Export could not complete safely.") -> None:
        super().__init__(message)
        self.message = message


class ExportUnsupportedFormat(ExportError):
    code = "EXPORT_UNSUPPORTED_FORMAT"


class ExportTooLarge(ExportError):
    code = "EXPORT_TOO_LARGE"


class ExportSerializationError(ExportError):
    code = "EXPORT_SERIALIZATION_FAILED"

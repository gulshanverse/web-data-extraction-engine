"""Structured, secret-safe logging conventions for API and worker operations."""

from __future__ import annotations

import logging

import structlog

SENSITIVE_KEYS = {"authorization", "cookie", "token", "password", "secret", "database_url", "redis_url"}


def _redact(_: object, __: str, event_dict: dict[str, object]) -> dict[str, object]:
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            _redact,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
    )

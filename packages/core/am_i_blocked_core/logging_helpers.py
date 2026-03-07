"""Structured logging helpers using structlog."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure structlog for the application.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR.
        log_format: 'json' for production, 'console' for local dev.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "json":
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger with the given name."""
    return structlog.get_logger(name)


def bind_request_context(request_id: str, actor: str | None = None) -> None:
    """Bind request-scoped context variables for correlation."""
    ctx: dict[str, Any] = {"request_id": request_id}
    if actor:
        ctx["actor"] = actor
    structlog.contextvars.bind_contextvars(**ctx)


def clear_request_context() -> None:
    """Clear request-scoped context variables."""
    structlog.contextvars.clear_contextvars()

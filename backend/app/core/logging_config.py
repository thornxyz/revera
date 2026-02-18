"""Structured logging configuration for Revera.

Supports two formats:
- text: Human-readable format for development
- json: Machine-parseable format for production/log aggregation

Usage:
    from app.core.logging_config import setup_logging, get_logger

    setup_logging()  # Call once at startup

    logger = get_logger(__name__)
    logger.info("user_action", extra={"user_id": "123", "action": "query"})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class TextFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    def format(self, record: logging.LogRecord) -> str:
        # Get base message
        message = record.getMessage()

        # Build prefix with timestamp and level
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"{timestamp} - {record.name} - {record.levelname}"

        # Add error code if present
        error_code = getattr(record, "error_code", None)
        if error_code:
            prefix += f" [{error_code}]"

        # Format main line
        output = f"{prefix} - {message}"

        # Add structured extra fields
        extra_fields = self._extract_extra_fields(record)
        if extra_fields:
            formatted_extra = " ".join(f"{k}={v}" for k, v in extra_fields.items())
            output += f" | {formatted_extra}"

        # Add exception info if present
        if record.exc_info:
            output += "\n" + self.formatException(record.exc_info)

        return output

    def _extract_extra_fields(self, record: logging.LogRecord) -> dict[str, Any]:
        """Extract custom fields from record."""
        extra_fields = {}
        reserved = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "message",
            "taskName",
            "error_code",
        }
        for key, value in record.__dict__.items():
            if key not in reserved and not key.startswith("_"):
                extra_fields[key] = value
        return extra_fields


class JsonFormatter(logging.Formatter):
    """JSON formatter for production/log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add error code if present
        error_code = getattr(record, "error_code", None)
        if error_code:
            log_entry["error_code"] = error_code

        # Add all extra fields
        reserved = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "message",
            "taskName",
            "error_code",
        }
        for key, value in record.__dict__.items():
            if key not in reserved and not key.startswith("_"):
                log_entry[key] = value

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(
    level: str = "INFO",
    log_format: str = "text",
    log_file: str | None = None,
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type ('text' for dev, 'json' for production)
        log_file: Optional file path for logging
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create formatter
    formatter = JsonFormatter() if log_format == "json" else TextFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("qdrant_client").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding temporary context to log messages.

    Usage:
        with LogContext(logger, user_id="123", chat_id="456"):
            logger.info("action_performed")  # Will include user_id and chat_id
    """

    def __init__(self, logger: logging.Logger, **context: Any):
        self.logger = logger
        self.context = context
        self.old_factory = None

    def __enter__(self):
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        self.old_factory = old_factory
        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, *args):
        logging.setLogRecordFactory(self.old_factory)


def log_error(
    logger: logging.Logger,
    message: str,
    error_code: str | None = None,
    exc_info: bool = True,
    **context: Any,
) -> None:
    """
    Log an error with structured context.

    Args:
        logger: Logger instance
        message: Error message
        error_code: Optional error code
        exc_info: Whether to include exception info
        **context: Additional context fields
    """
    extra = context.copy()
    if error_code:
        extra["error_code"] = error_code
    logger.error(message, extra=extra, exc_info=exc_info)


def log_warning(
    logger: logging.Logger,
    message: str,
    error_code: str | None = None,
    **context: Any,
) -> None:
    """Log a warning with structured context."""
    extra = context.copy()
    if error_code:
        extra["error_code"] = error_code
    logger.warning(message, extra=extra)


def log_info(
    logger: logging.Logger,
    message: str,
    **context: Any,
) -> None:
    """Log info with structured context."""
    logger.info(message, extra=context)


def log_debug(
    logger: logging.Logger,
    message: str,
    **context: Any,
) -> None:
    """Log debug with structured context."""
    logger.debug(message, extra=context)

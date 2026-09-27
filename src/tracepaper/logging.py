"""Structured logging setup using structlog."""

import logging
import sys
import structlog
from pythonjsonlogger import jsonlogger


def setup_logging(log_level: str = "info") -> None:
    """
    Configure structlog with JSON output.

    Args:
        log_level: Logging level (debug, info, warning, error, critical).
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add JSON handler
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter()
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def get_logger(name: str):
    """Get a logger instance."""
    return structlog.get_logger(name)

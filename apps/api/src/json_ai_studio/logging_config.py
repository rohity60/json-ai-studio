"""Logging configuration for JSON AI Studio.

Usage: from .logging_config import configure; configure()
Called once at FastAPI startup before any routes are registered.
"""

import logging
import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stderr",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["default"],
    },
    "loggers": {
        "json_ai_studio": {
            "level": "INFO",
            "handlers": ["default"],
            "propagate": False,
        },
    },
}


def configure() -> None:
    """Apply logging config. Safe to call multiple times."""
    logging.config.dictConfig(LOGGING_CONFIG)

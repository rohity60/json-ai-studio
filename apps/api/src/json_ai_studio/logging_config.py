"""Logging configuration for JSON AI Studio (ADR-0017).

Usage: from .logging_config import configure; configure()
Called once at FastAPI startup before any routes are registered.

Config is built dynamically from ``Settings`` (env-driven): level, log dir,
console/file toggles, and size-based rotation are all tunable via LOG_* env
vars without code changes. Two sinks: a console handler (stderr, so
``docker logs`` still works) and a rotating file handler
(``logging.handlers.RotatingFileHandler``) that survives restarts.

When ``log_capture_uvicorn`` is set, uvicorn's own loggers (including
``uvicorn.access``) are routed to the same handlers so request access lines
land in the file too. ``configure()`` runs at app-module import — after
uvicorn has installed its default logging — so re-declaring those loggers
here overrides uvicorn's handlers.

Caveat: size-based rotation is not multi-process safe. With multiple uvicorn
workers (or the ``--reload`` reloader) two processes can race on rollover.
Acceptable for this single-worker MVP; revisit with a queue/socket handler or
external log shipping if we scale out workers.
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

from .settings import get_settings

# Plain-text format enriched with filename:lineno to make DEBUG output easy to
# trace back to source. Human-readable in both console and file.
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Uvicorn loggers we adopt when log_capture_uvicorn is on.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Chatty third-party loggers pinned to WARNING. Without an explicit level these
# inherit the root level, so LOG_LEVEL=DEBUG would drown our own debug logs in
# litellm/httpx/asyncio internals. DEBUG stays scoped to json_ai_studio.
_NOISY_LOGGERS = ("LiteLLM", "litellm", "httpx", "httpcore", "asyncio")


def _build_config() -> dict:
    settings = get_settings()
    level = settings.log_level

    handlers: dict[str, dict] = {}
    active: list[str] = []

    if settings.log_to_console:
        handlers["console"] = {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stderr",
        }
        active.append("console")

    if settings.log_to_file:
        log_dir = Path(settings.log_dir)
        # RotatingFileHandler does not create parent dirs -- do it here.
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "filename": str(log_dir / settings.log_file_name),
            "maxBytes": settings.log_max_bytes,
            "backupCount": settings.log_backup_count,
            "encoding": "utf-8",
        }
        active.append("file")

    loggers: dict[str, dict] = {
        "json_ai_studio": {
            "level": level,
            "handlers": active,
            "propagate": False,
        },
    }
    if settings.log_capture_uvicorn:
        for name in _UVICORN_LOGGERS:
            loggers[name] = {
                "level": level,
                "handlers": active,
                "propagate": False,
            }

    # Keep third-party debug spam out of our logs regardless of LOG_LEVEL.
    for name in _NOISY_LOGGERS:
        loggers[name] = {"level": "WARNING", "propagate": True}

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": _FORMAT, "datefmt": _DATEFMT},
        },
        "handlers": handlers,
        "root": {"level": level, "handlers": active},
        "loggers": loggers,
    }


def configure() -> None:
    """Apply logging config from Settings. Safe to call multiple times."""
    logging.config.dictConfig(_build_config())

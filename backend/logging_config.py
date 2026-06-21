"""Logging configuration.

`configure()` is called once at app startup (from `main.create_app`). It
installs a single stream handler on the root logger with the chosen
format. Modules elsewhere just call `logging.getLogger(__name__)` —
the handler we install picks up their output.
"""
from __future__ import annotations

import logging

from pythonjsonlogger.json import JsonFormatter


_TEXT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure(level: str = "INFO", fmt: str = "text") -> None:
    """Idempotent: safe to call repeatedly (e.g. from tests + lifespan)."""
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any previously-installed handlers from us so re-configure works
    for handler in list(root.handlers):
        if getattr(handler, "_installed_by_siteiq", False):
            root.removeHandler(handler)

    handler: logging.Handler = logging.StreamHandler()
    if fmt == "json":
        handler.setFormatter(JsonFormatter(_JSON_FORMAT))
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))
    handler._installed_by_siteiq = True  # type: ignore[attr-defined]
    root.addHandler(handler)

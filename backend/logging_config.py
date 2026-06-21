"""Logging configuration.

`configure()` is called once at app startup (from `main.create_app`). It
installs a single stream handler on the root logger with the chosen
format. Modules elsewhere just call `logging.getLogger(__name__)` —
the handler we install picks up their output.

Every record is stamped with the current request id (via
`api.request_id.RequestIdFilter`) so prod logs are trivially groupable
by request — paste `request_id=abc123` into the log search.
"""
from __future__ import annotations

import logging

from pythonjsonlogger.json import JsonFormatter

from api.request_id import RequestIdFilter


_TEXT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s [rid=%(request_id)s]"
_JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s"


class _DefaultRequestIdRecord(logging.LogRecord):
    """Records that aren't stamped (boot-time logs etc.) get a blank
    request_id so the format strings don't blow up."""


def _ensure_record_default(record: logging.LogRecord) -> bool:
    if not hasattr(record, "request_id"):
        record.request_id = ""
    return True


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
    handler.addFilter(RequestIdFilter())
    # Belt-and-suspenders: stamp empty string on records that bypass the
    # contextvar (boot time, background tasks).
    handler.addFilter(_ensure_record_default)
    handler._installed_by_siteiq = True  # type: ignore[attr-defined]
    root.addHandler(handler)

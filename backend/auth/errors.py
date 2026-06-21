"""Typed error envelope for auth + orgs.

All API errors round-trip as `{error: {code, message, field?}}` so the
frontend can render field-level errors inline (claude.md #3 lesson —
no silent undefined).
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException


class ApiError(HTTPException):
    """Raises the standard JSON error envelope.

    `code` is a stable string identifier the frontend keys off; `message`
    is human-readable; `field` is optional and ties the error to a form
    input.
    """

    def __init__(self, status_code: int, code: str, message: str, *, field: Optional[str] = None) -> None:
        detail = {"error": {"code": code, "message": message}}
        if field is not None:
            detail["error"]["field"] = field
        super().__init__(status_code=status_code, detail=detail)

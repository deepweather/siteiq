"""Capture seam — turn human input (text now; voice/photo later) into
proposed ledger events.

Mirrors the `EmailSender` seam: a `CaptureParser` Protocol plus a
deterministic, dependency-free default (`RuleBasedCaptureParser`) and an
`LLMCaptureParser` stub wireable later via `settings.capture_provider`.
Captured events are emitted as `proposed` so they land in the confirmation
inbox — "confirm, don't create": the system proposes, the human approves.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from models.site_event import EventEnvelope, EventKind, SubjectType
from services.event_ledger import EventStatusValue


logger = logging.getLogger("siteiq.record.capture")


_MATERIAL_WORDS = {
    "rebar": "rebar", "steel": "rebar", "reinforcement": "rebar",
    "concrete": "concrete", "beton": "concrete",
    "conduit": "conduit",
    "drywall": "drywall", "plasterboard": "drywall", "gipskarton": "drywall",
    "pipe": "pipe", "pipes": "pipe",
    "aggregate": "aggregate", "gravel": "aggregate",
}
_DELIVERY_WORDS = ("delivered", "delivery", "arrived", "dropped", "geliefert")
_INCIDENT_WORDS = ("incident", "accident", "hazard", "unsafe", "injury", "near miss", "near-miss")
_INSPECTION_WORDS = ("inspection", "inspected")
_FAIL_WORDS = ("failed", "reject", "fail", "ngo", "not pass")
_UNIT_BY_MATERIAL = {
    "rebar": "t", "concrete": "m3", "conduit": "m",
    "drywall": "sheet", "pipe": "m", "aggregate": "t",
}


@runtime_checkable
class CaptureParser(Protocol):
    """Parse free-form input into proposed events for `(org_id, project_id)`."""

    def parse(
        self,
        text: str,
        *,
        org_id: str,
        project_id: str,
        occurred_at: datetime | None = None,
        actor_user_id: str | None = None,
    ) -> list[EventEnvelope]:
        ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RuleBasedCaptureParser:
    """Keyword/regex parser. Deterministic, hermetic, zero dependencies.

    Recognises deliveries, incidents, and inspections; everything else
    becomes a freeform `note`. Always emits `proposed` events so a human
    confirms them — the parser is allowed to be imperfect."""

    def parse(
        self,
        text: str,
        *,
        org_id: str,
        project_id: str,
        occurred_at: datetime | None = None,
        actor_user_id: str | None = None,
    ) -> list[EventEnvelope]:
        ts = occurred_at or _now()
        lowered = text.lower().strip()
        if not lowered:
            return []

        zone_id = self._find_zone(lowered)

        def env(subject_type, subject_id, kind, payload, confidence) -> EventEnvelope:
            return EventEnvelope(
                org_id=org_id,
                project_id=project_id,
                subject_type=subject_type,
                subject_id=subject_id,
                kind=kind,
                occurred_at=ts,
                payload={**payload, "note": text},
                source="human",
                confidence=confidence,
                status=EventStatusValue.PROPOSED,
                actor_user_id=actor_user_id,
            )

        material = self._find_material(lowered)
        if material and any(w in lowered for w in _DELIVERY_WORDS):
            qty = self._find_quantity(lowered)
            return [env(
                SubjectType.MATERIAL.value,
                f"capture-{material}",
                EventKind.MATERIAL_DELIVERED.value,
                {
                    "subtype": material,
                    "quantity": qty if qty is not None else 0.0,
                    "unit": _UNIT_BY_MATERIAL.get(material, "unit"),
                    "zone_id": zone_id,
                },
                0.65,
            )]

        if any(w in lowered for w in _INCIDENT_WORDS):
            return [env(
                SubjectType.INCIDENT.value,
                "capture-incident",
                EventKind.INCIDENT_FLAGGED.value,
                {"zone_id": zone_id, "severity": "unknown"},
                0.7,
            )]

        if any(w in lowered for w in _INSPECTION_WORDS):
            failed = any(w in lowered for w in _FAIL_WORDS)
            kind = (
                EventKind.INSPECTION_FAILED.value if failed
                else EventKind.INSPECTION_PASSED.value
            )
            return [env(
                SubjectType.INSPECTION.value,
                "capture-inspection",
                kind,
                {"zone_id": zone_id, "result": "fail" if failed else "pass"},
                0.7,
            )]

        # Fallback: a freeform note attached to the site.
        return [env(
            SubjectType.SITE.value, "site", EventKind.NOTE.value,
            {"zone_id": zone_id}, 0.5,
        )]

    @staticmethod
    def _find_material(text: str) -> str | None:
        for word, subtype in _MATERIAL_WORDS.items():
            if re.search(rf"\b{re.escape(word)}\b", text):
                return subtype
        return None

    @staticmethod
    def _find_quantity(text: str) -> float | None:
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(m.group(1)) if m else None

    @staticmethod
    def _find_zone(text: str) -> str | None:
        m = re.search(r"zone[\s-]*([a-z0-9]+)", text)
        if m:
            return f"zone-{m.group(1)}"
        return None


class LLMCaptureParser:
    """Placeholder for an LLM/multimodal parser. Wired via
    `settings.capture_provider="llm"`; until a provider is configured it
    falls back to the rule-based parser so the feature never hard-fails."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._fallback = RuleBasedCaptureParser()

    def parse(self, text: str, **kwargs) -> list[EventEnvelope]:
        # A real implementation would call the model here. Without a
        # configured provider we degrade gracefully to deterministic rules.
        logger.info("llm_capture_fallback_to_rules")
        return self._fallback.parse(text, **kwargs)


def build_capture_parser_from_settings(settings) -> CaptureParser:
    """Factory used at app startup (mirrors `build_sender_from_settings`)."""
    if settings.capture_provider.lower() == "llm" and settings.record_llm_api_key:
        return LLMCaptureParser(api_key=settings.record_llm_api_key)
    return RuleBasedCaptureParser()

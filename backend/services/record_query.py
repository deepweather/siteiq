"""Query seam — answer natural-language questions from the ledger.

Mirrors the capture seam: a `QueryResponder` Protocol, a deterministic
default that maps a fixed set of intents to ledger aggregations (with the
supporting event ids so the UI can show evidence), and an `LLMQueryResponder`
stub wireable later via `settings.query_provider`. The deterministic path
keeps tests hermetic and needs no API keys.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from models.cost import RateCard, default_rate_card
from models.site_event import EventKind
from services.cost_engine import compute_costs
from services.event_ledger import EventLedger


logger = logging.getLogger("siteiq.record.query")


class QueryAnswer(BaseModel):
    intent: str
    answer: str
    data: dict = Field(default_factory=dict)
    supporting_event_ids: list[str] = Field(default_factory=list)


@runtime_checkable
class QueryResponder(Protocol):
    async def answer(
        self,
        db: AsyncSession,
        *,
        org_id: str,
        project_id: str,
        question: str,
        rate_card: RateCard | None = None,
    ) -> QueryAnswer:
        ...


def _eur(x: float) -> str:
    return f"€{x:,.0f}"


class DeterministicQueryResponder:
    """Intent-matched aggregations over the ledger. Fully deterministic."""

    async def answer(
        self,
        db: AsyncSession,
        *,
        org_id: str,
        project_id: str,
        question: str,
        rate_card: RateCard | None = None,
    ) -> QueryAnswer:
        rc = rate_card or default_rate_card()
        ledger = EventLedger(db)
        q = question.lower()

        if any(w in q for w in ("idle", "utilization", "utilisation", "crane", "excavator", "pump", "equipment")):
            return await self._equipment(ledger, org_id, project_id, rc)
        if any(w in q for w in ("deliver", "delivery", "material", "rebar", "concrete")):
            return await self._deliveries(ledger, org_id, project_id, rc)
        if any(w in q for w in ("worker", "crew", "headcount", "people", "labour", "labor", "hours")):
            return await self._labor(ledger, org_id, project_id, rc)
        if any(w in q for w in ("incident", "safety", "accident", "hazard")):
            return await self._incidents(ledger, org_id, project_id)
        if any(w in q for w in ("cost", "spend", "spent", "waste", "money", "euro", "total", "budget")):
            return await self._cost(ledger, org_id, project_id, rc)
        return await self._fallback(ledger, org_id, project_id)

    async def _equipment(self, ledger, org_id, project_id, rc) -> QueryAnswer:
        evs = await ledger.query(
            org_id, project_id,
            kinds=[EventKind.EQUIPMENT_UTILIZATION.value],
            statuses=["confirmed"], limit=10000,
        )
        idle_hours = sum(float(e.payload.get("hours_idle", 0.0)) for e in evs)
        idle_cost = sum(
            float(e.payload.get("hours_idle", 0.0)) * rc.equipment_rate(e.payload.get("subtype"))
            for e in evs
        )
        return QueryAnswer(
            intent="equipment_idle",
            answer=(
                f"Equipment sat idle for {idle_hours:,.0f} hours across the recorded "
                f"period, costing {_eur(idle_cost)}."
            ),
            data={"idle_hours": round(idle_hours, 1), "idle_cost": round(idle_cost, 2)},
            supporting_event_ids=[e.id for e in evs[:50]],
        )

    async def _deliveries(self, ledger, org_id, project_id, rc) -> QueryAnswer:
        evs = await ledger.query(
            org_id, project_id,
            kinds=[EventKind.MATERIAL_DELIVERED.value],
            statuses=["confirmed"], limit=10000,
        )
        total = 0.0
        for e in evs:
            qty = float(e.payload.get("quantity", 0.0))
            unit_cost = e.payload.get("unit_cost")
            if unit_cost is None:
                unit_cost = rc.material_unit_cost(e.payload.get("subtype"))
            total += qty * float(unit_cost)
        return QueryAnswer(
            intent="deliveries",
            answer=(
                f"{len(evs)} confirmed deliveries totalling {_eur(total)} in materials."
            ),
            data={"delivery_count": len(evs), "material_cost": round(total, 2)},
            supporting_event_ids=[e.id for e in evs[:50]],
        )

    async def _labor(self, ledger, org_id, project_id, rc) -> QueryAnswer:
        evs = await ledger.query(
            org_id, project_id,
            kinds=[EventKind.WORKER_TIMESHEET.value],
            statuses=["confirmed"], limit=20000,
        )
        workers = {e.payload.get("worker_id") or e.subject_id for e in evs}
        total_hours = sum(float(e.payload.get("hours_total", 0.0)) for e in evs)
        labor_cost = sum(
            float(e.payload.get("hours_total", 0.0)) * rc.labor_rate(e.payload.get("trade"))
            for e in evs
        )
        return QueryAnswer(
            intent="labor",
            answer=(
                f"{len(workers)} distinct workers logged {total_hours:,.0f} hours, "
                f"costing {_eur(labor_cost)} in labour."
            ),
            data={
                "distinct_workers": len(workers),
                "total_hours": round(total_hours, 1),
                "labor_cost": round(labor_cost, 2),
            },
            supporting_event_ids=[e.id for e in evs[:50]],
        )

    async def _incidents(self, ledger, org_id, project_id) -> QueryAnswer:
        evs = await ledger.query(
            org_id, project_id,
            kinds=[EventKind.INCIDENT_FLAGGED.value], limit=10000,
        )
        return QueryAnswer(
            intent="incidents",
            answer=f"{len(evs)} safety incidents were flagged in the record.",
            data={"incident_count": len(evs)},
            supporting_event_ids=[e.id for e in evs[:50]],
        )

    async def _cost(self, ledger, org_id, project_id, rc) -> QueryAnswer:
        evs = await ledger.query(org_id, project_id, statuses=["confirmed"], limit=100000)
        breakdown = compute_costs(evs, rc)
        return QueryAnswer(
            intent="cost",
            answer=(
                f"Total recorded cost is {_eur(breakdown.total_cost)} "
                f"({_eur(breakdown.labor_cost)} labour, "
                f"{_eur(breakdown.equipment_idle_cost)} equipment idle, "
                f"{_eur(breakdown.material_cost)} materials). "
                f"Of that, {_eur(breakdown.labor_waste_cost)} is non-productive labour."
            ),
            data=breakdown.model_dump(exclude={"lines"}),
            supporting_event_ids=[
                eid for l in breakdown.lines[:50] for eid in l.supporting_event_ids
            ],
        )

    async def _fallback(self, ledger, org_id, project_id) -> QueryAnswer:
        evs = await ledger.query(org_id, project_id, statuses=["confirmed"], limit=100000)
        first = evs[0].occurred_at.date().isoformat() if evs else None
        last = evs[-1].occurred_at.date().isoformat() if evs else None
        return QueryAnswer(
            intent="summary",
            answer=(
                f"The record holds {len(evs)} confirmed events"
                + (f" from {first} to {last}." if first else ".")
                + " Try asking about idle equipment, deliveries, labour, or cost."
            ),
            data={"event_count": len(evs), "first": first, "last": last},
            supporting_event_ids=[],
        )


class LLMQueryResponder:
    """Placeholder LLM responder, wired via `settings.query_provider="llm"`.
    Falls back to the deterministic responder until a provider is configured."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._fallback = DeterministicQueryResponder()

    async def answer(self, db, **kwargs) -> QueryAnswer:
        logger.info("llm_query_fallback_to_deterministic")
        return await self._fallback.answer(db, **kwargs)


def build_query_responder_from_settings(settings) -> QueryResponder:
    if settings.query_provider.lower() == "llm" and settings.record_llm_api_key:
        return LLMQueryResponder(api_key=settings.record_llm_api_key)
    return DeterministicQueryResponder()

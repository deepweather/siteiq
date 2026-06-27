"""Cost models — the rate card + the breakdown the cost engine produces.

Costs are a projection over the event ledger: `services.cost_engine` folds
events against a `RateCard`. Every `CostLine` carries the ids of the events
that justify it, so every euro on a report is clickable back to the
observation (and, with real cameras, the frame) that produced it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from config import (
    DEFAULT_MATERIAL_UNIT_COST,
    EQUIPMENT_HOURLY_RATE_BY_SUBTYPE,
    LABOR_HOURLY_RATE_BY_TRADE,
    LOADED_HOURLY_RATE,
    MATERIAL_UNIT_COST_BY_SUBTYPE,
)


class RateCard(BaseModel):
    """Prices the cost engine multiplies event quantities by."""

    labor_rates: dict[str, float] = Field(default_factory=dict)
    default_labor_rate: float = float(LOADED_HOURLY_RATE)
    equipment_rates: dict[str, float] = Field(default_factory=dict)
    default_equipment_rate: float = float(LOADED_HOURLY_RATE)
    material_unit_costs: dict[str, float] = Field(default_factory=dict)
    default_material_unit_cost: float = DEFAULT_MATERIAL_UNIT_COST

    def labor_rate(self, trade: str | None) -> float:
        if trade and trade in self.labor_rates:
            return self.labor_rates[trade]
        return self.default_labor_rate

    def equipment_rate(self, subtype: str | None) -> float:
        if subtype and subtype in self.equipment_rates:
            return self.equipment_rates[subtype]
        return self.default_equipment_rate

    def material_unit_cost(self, subtype: str | None) -> float:
        if subtype and subtype in self.material_unit_costs:
            return self.material_unit_costs[subtype]
        return self.default_material_unit_cost


def default_rate_card() -> RateCard:
    """The ground-truth default rate card, sourced from `config.py`."""
    return RateCard(
        labor_rates=dict(LABOR_HOURLY_RATE_BY_TRADE),
        default_labor_rate=float(LOADED_HOURLY_RATE),
        equipment_rates=dict(EQUIPMENT_HOURLY_RATE_BY_SUBTYPE),
        default_equipment_rate=float(LOADED_HOURLY_RATE),
        material_unit_costs=dict(MATERIAL_UNIT_COST_BY_SUBTYPE),
        default_material_unit_cost=DEFAULT_MATERIAL_UNIT_COST,
    )


# Cost categories — kept as constants so the engine + UI agree.
CATEGORY_LABOR = "labor"
CATEGORY_LABOR_WASTE = "labor_waste"
CATEGORY_EQUIPMENT_IDLE = "equipment_idle"
CATEGORY_MATERIAL = "material"


class CostLine(BaseModel):
    """One priced fact, traceable back to the events that justify it."""

    category: str
    label: str
    amount: float
    occurred_on: str | None = None  # ISO date (valid time)
    zone_id: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    supporting_event_ids: list[str] = Field(default_factory=list)


class CostGroup(BaseModel):
    key: str
    label: str
    amount: float


class CostBreakdown(BaseModel):
    since: str | None = None
    until: str | None = None
    labor_cost: float = 0.0
    labor_waste_cost: float = 0.0
    equipment_idle_cost: float = 0.0
    material_cost: float = 0.0
    total_cost: float = 0.0
    by_category: list[CostGroup] = Field(default_factory=list)
    by_day: list[CostGroup] = Field(default_factory=list)
    by_zone: list[CostGroup] = Field(default_factory=list)
    lines: list[CostLine] = Field(default_factory=list)

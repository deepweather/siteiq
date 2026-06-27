"""The canonical project document.

One Pydantic model is the storage format, the editor's state, the API
payload, and the simulation engine's input. There is exactly one
transformation in the codebase: `simulation.project_loader.build_engine_state`
turns a `ProjectDocument` into `(Site, list[Asset], dict[worker_id, WorkerInternals])`.
Every other layer (storage, editor, API, validator) handles the document
as-is.

Versioning model: a document is treated as immutable once persisted. The
SHA-256 of `model_dump_json(by_alias=False, exclude_none=False)` is the
content-addressed version id. Edits create a new version row; the
`projects.current_version_id` FK is the only mutable pointer.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from models.assets import DEFAULT_LEVEL_ID
from models.connection import Connection
from models.site import Discipline, Level, Phase, Road, ScheduleEntry, Zone


SCHEMA_VERSION = 1


class FacilitySpec(BaseModel):
    id: str
    subtype: str  # "toilet" | "breakroom" | "office" | "toolcrib"
    x: float
    y: float
    level_id: str = DEFAULT_LEVEL_ID


class EquipmentSpec(BaseModel):
    id: str
    # "tower_crane" | "concrete_pump" | "excavator" |
    # (Tiefbau: "sheet_pile", "dewatering_pump")
    subtype: str
    x: float
    y: float
    state: Literal["operating", "idle"] = "operating"
    # "*" means cross-level (typical for tower cranes). Otherwise the
    # equipment is pinned to one level.
    level_id: str = DEFAULT_LEVEL_ID


class MaterialSpec(BaseModel):
    id: str
    subtype: str  # "rebar" | "conduit" | "drywall" | "concrete"
    x: float
    y: float
    needed_in: str
    level_id: str = DEFAULT_LEVEL_ID


class WorkerSeed(BaseModel):
    """How many workers of which trade are initialised in which zone."""

    zone_id: str
    trade: str
    count: int


class ProjectDocument(BaseModel):
    """Root immutable record. Serialised with sorted keys and SHA-256'd
    to produce the content-addressed version id."""

    schema_version: int = SCHEMA_VERSION
    slug: str
    name: str
    description: str
    type: str = "Residential"  # Display tag — Residential | Commercial | Infrastructure
    discipline: Discipline = Discipline.HOCHBAU
    width: float
    height: float
    start_day: int = 1
    levels: list[Level] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
    facilities: list[FacilitySpec] = Field(default_factory=list)
    equipment: list[EquipmentSpec] = Field(default_factory=list)
    materials: list[MaterialSpec] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
    schedule: list[ScheduleEntry] = Field(default_factory=list)
    worker_seeds: list[WorkerSeed] = Field(default_factory=list)
    # Authored road network. Empty means the navmesh + renderer fall back
    # to the legacy hardcoded perimeter strips, so v1 documents (and any
    # imported seeds without `roads`) load and run unchanged.
    roads: list[Road] = Field(default_factory=list)

    @field_validator("levels")
    @classmethod
    def _ensure_default_level(cls, v: list[Level]) -> list[Level]:
        if not v:
            # Every project has at least the ground floor. We don't
            # forbid empty levels at the field level so the editor can
            # build up incrementally; the validator below catches it
            # before persistence.
            return [Level(id=DEFAULT_LEVEL_ID, name="EG", elevation_m=0.0, order=0)]
        return v

    def content_hash(self) -> str:
        """SHA-256 of the canonical-JSON body. Same input -> same id;
        any edit -> different id. Used as the project_versions PK."""
        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────
# Validation helpers
# ──────────────────────────────────────────────────────────────────────


class ValidationIssue(BaseModel):
    """One validation problem. Severity decides whether the document is
    publishable: only "error" blocks; "warning" is shown but allowed."""

    code: str
    severity: Literal["error", "warning"] = "error"
    message: str
    field: str | None = None
    asset_id: str | None = None


def validate_document(doc: ProjectDocument) -> list[ValidationIssue]:
    """Pure-function validator. Returns the full list of issues; the
    caller decides what to do with errors vs warnings."""
    issues: list[ValidationIssue] = []

    if not doc.levels:
        issues.append(ValidationIssue(
            code="no_levels",
            message="Project must have at least one level.",
            field="levels",
        ))
        # Bail out — most downstream checks need a level list to work with.
        return issues

    level_ids = {lv.id for lv in doc.levels}

    if len({lv.id for lv in doc.levels}) != len(doc.levels):
        issues.append(ValidationIssue(
            code="duplicate_level_id",
            message="Level ids must be unique.",
            field="levels",
        ))

    zone_ids: set[str] = set()
    for z in doc.zones:
        if z.id in zone_ids:
            issues.append(ValidationIssue(
                code="duplicate_zone_id",
                message=f"Zone id {z.id!r} appears twice.",
                asset_id=z.id,
            ))
        zone_ids.add(z.id)
        if z.level_id not in level_ids:
            issues.append(ValidationIssue(
                code="unknown_level",
                message=f"Zone {z.id!r} references unknown level {z.level_id!r}.",
                asset_id=z.id,
            ))
        if z.x < 0 or z.y < 0 or z.x + z.width > doc.width or z.y + z.height > doc.height:
            issues.append(ValidationIssue(
                code="zone_out_of_bounds",
                severity="warning",
                message=(
                    f"Zone {z.id!r} is partially outside the site rectangle "
                    f"({doc.width}x{doc.height})."
                ),
                asset_id=z.id,
            ))

    for spec_list, label in (
        (doc.facilities, "facility"),
        (doc.equipment, "equipment"),
        (doc.materials, "material"),
    ):
        for s in spec_list:
            if s.level_id != "*" and s.level_id not in level_ids:
                issues.append(ValidationIssue(
                    code="unknown_level",
                    message=f"{label.title()} {s.id!r} references unknown level {s.level_id!r}.",
                    asset_id=s.id,
                ))

    for m in doc.materials:
        if m.needed_in not in zone_ids:
            issues.append(ValidationIssue(
                code="unknown_zone",
                message=f"Material {m.id!r} needs zone {m.needed_in!r} which is not defined.",
                asset_id=m.id,
            ))

    for entry in doc.schedule:
        if entry.zone_id not in zone_ids:
            issues.append(ValidationIssue(
                code="unknown_zone",
                message=f"Schedule entry references unknown zone {entry.zone_id!r}.",
                field="schedule",
            ))
        if entry.start_day > entry.end_day:
            issues.append(ValidationIssue(
                code="schedule_inverted",
                message=(
                    f"Schedule entry on {entry.zone_id} has start_day > end_day "
                    f"({entry.start_day} > {entry.end_day})."
                ),
                field="schedule",
            ))

    for seed in doc.worker_seeds:
        if seed.zone_id not in zone_ids:
            issues.append(ValidationIssue(
                code="unknown_zone",
                message=f"Worker seed references unknown zone {seed.zone_id!r}.",
                field="worker_seeds",
            ))
        if seed.count < 0:
            issues.append(ValidationIssue(
                code="negative_count",
                message=f"Worker seed for {seed.zone_id}/{seed.trade} has negative count.",
                field="worker_seeds",
            ))

    for c in doc.connections:
        bad = [n.level_id for n in c.nodes if n.level_id not in level_ids]
        if bad:
            issues.append(ValidationIssue(
                code="unknown_level",
                message=f"Connection {c.id!r} touches unknown levels: {bad}.",
                asset_id=c.id,
            ))
        if len(c.nodes) < 2:
            issues.append(ValidationIssue(
                code="degenerate_connection",
                message=f"Connection {c.id!r} must touch at least two levels.",
                asset_id=c.id,
            ))

    return issues


__all__ = [
    "SCHEMA_VERSION",
    "FacilitySpec",
    "EquipmentSpec",
    "MaterialSpec",
    "WorkerSeed",
    "ProjectDocument",
    "ValidationIssue",
    "validate_document",
]

"""Record visibility policy — tiered data privacy over the event ledger.

Authentication is solved elsewhere (sessions + orgs + roles); this is the
*authorization* layer that decides which slice of the system of record a
member may see. The driving principle: aggregate + asset data is open;
individual worker behavioural data is privileged. This is a GDPR / works-
council requirement in the DACH market, not a nice-to-have.

Three tiers, mapped onto the existing role ladder:

- **crew**       (viewer) — operational only: equipment, materials, zones,
  inspections, incidents, deliveries, aggregate costs + headcounts. No
  individual worker records.
- **supervisor** (member) — the above + individual worker presence /
  timesheets, but NOT the behavioural breakdown (toilet/break/movement) or
  per-person cost attribution.
- **manager**    (admin/owner) — everything.

Enforcement is server-side; the UI mirrors it for affordance only.
"""
from __future__ import annotations

from db.models import Role


# Subjects whose individual records are personal (privileged).
PERSONAL_SUBJECT_TYPES = {"worker"}

# Event kinds that reveal individual worker activity.
PERSONAL_EVENT_KINDS = {
    "worker.timesheet",
    "worker.clocked_in",
    "worker.clocked_out",
}

# Behavioural payload fields hidden from supervisors (managers see them).
# Toilet/break = facilities; movement = walking + vertical transport.
BEHAVIORAL_FIELDS = {"hours_facilities", "hours_walking", "hours_vertical"}

# Behavioural metrics on a worker projection hidden from supervisors.
BEHAVIORAL_METRICS = {"walking_hours"}

# Cost line categories that attribute euros to an individual worker.
PERSONAL_COST_CATEGORIES = {"labor", "labor_waste"}

# Entry kinds the worker PWA is allowed to submit. These map to the same
# operational event kinds the RuleBasedCaptureParser already produces, and
# are always written as `proposed` so a supervisor confirms them. Crew
# (viewer) may submit these; nothing personal/behavioural is writable here.
WORKER_ENTRY_KINDS = {"delivery", "incident", "inspection", "note"}


class RecordAccess:
    """Per-request visibility policy derived from the caller's org role."""

    def __init__(self, role: str) -> None:
        self.role = role
        rank = Role.rank(role)
        # admin + owner
        self.is_manager = rank >= Role.rank(Role.ADMIN)
        # member + admin + owner
        self.can_see_personal = rank >= Role.rank(Role.MEMBER)

    # ── subjects ────────────────────────────────────────────────────

    def can_view_subject_type(self, subject_type: str) -> bool:
        if subject_type in PERSONAL_SUBJECT_TYPES:
            return self.can_see_personal
        return True

    # ── worker entry submission (crew-write, always proposed) ─────────

    @staticmethod
    def can_submit_entry(kind: str) -> bool:
        """Whether a field worker may submit an entry of this kind. Any org
        member (viewer+) may submit the allow-listed kinds; the route forces
        them to `proposed` for supervisor review."""
        return kind in WORKER_ENTRY_KINDS

    def filter_subjects(self, subjects: list[dict]) -> list[dict]:
        if self.can_see_personal:
            return subjects
        return [s for s in subjects if s["subject_type"] not in PERSONAL_SUBJECT_TYPES]

    # ── events ──────────────────────────────────────────────────────

    def filter_events(self, events: list[dict]) -> list[dict]:
        """Drop personal events the caller can't see; redact behavioural
        fields from the ones they can."""
        out: list[dict] = []
        for e in events:
            personal = (
                e["kind"] in PERSONAL_EVENT_KINDS
                or e["subject_type"] in PERSONAL_SUBJECT_TYPES
            )
            if personal and not self.can_see_personal:
                continue
            out.append(self._redact_event(e) if personal else e)
        return out

    def _redact_event(self, e: dict) -> dict:
        if self.is_manager:
            return e
        if e["kind"] == "worker.timesheet" and e.get("payload"):
            payload = {k: v for k, v in e["payload"].items() if k not in BEHAVIORAL_FIELDS}
            return {**e, "payload": payload}
        return e

    # ── entity projection ───────────────────────────────────────────

    def redact_entity(self, projection: dict) -> dict:
        """Redact behavioural metrics/state/events from a worker projection
        for supervisors. (Crew never reach here — the route 403s first.)"""
        if self.is_manager:
            return projection
        if projection["subject_type"] not in PERSONAL_SUBJECT_TYPES:
            return projection
        metrics = {
            k: v for k, v in (projection.get("metrics") or {}).items()
            if k not in BEHAVIORAL_METRICS
        }
        state = {
            k: v for k, v in (projection.get("state") or {}).items()
            if k not in BEHAVIORAL_FIELDS
        }
        events = [self._redact_event(e) for e in projection.get("events", [])]
        return {**projection, "metrics": metrics, "state": state, "events": events}

    # ── costs ───────────────────────────────────────────────────────

    def redact_cost(self, breakdown):
        """Strip per-worker cost lines for non-managers. Aggregate totals
        (labour/equipment/material, by-day, by-zone) stay visible — they're
        not personally identifying."""
        if self.is_manager:
            return breakdown
        breakdown.lines = [
            line for line in breakdown.lines
            if line.category not in PERSONAL_COST_CATEGORIES
        ]
        return breakdown

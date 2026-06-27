"""EventLedger — the single write path into the system of record.

Every producer (demo generator, live simulation drain loop, manual
capture, future camera `LiveSource`) appends through this service so the
per-stream `seq` counter and hash chain stay consistent. This mirrors the
`EmailSender` / `SiteStateSource` seam philosophy: one narrow contract,
many implementations feeding it.

Append-only: the only mutation is the denormalised `status` cache, and
every status change is itself recorded as a companion event so the log
remains the source of truth.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import SiteEvent
from models.site_event import (
    EventEnvelope,
    EventKind,
    SubjectType,
    event_hash,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# String constants for the status cache so callers reference statuses
# without pulling the ORM enum. Mirrors `db.models.EventStatus`.
class EventStatusValue:  # noqa: D401 - simple constant holder
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class EventLedger:
    """SQLAlchemy-backed append-only ledger. Stateless — pass a session in."""

    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── stream head ─────────────────────────────────────────────────

    async def _stream_head(self, org_id: str, project_id: str) -> tuple[int, str]:
        """Return `(last_seq, last_hash)` for the stream, or `(0, "")` when
        the stream is empty."""
        result = await self.db.execute(
            select(SiteEvent.seq, SiteEvent.hash)
            .where(
                SiteEvent.org_id == org_id,
                SiteEvent.project_id == project_id,
            )
            .order_by(SiteEvent.seq.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return 0, ""
        return int(row[0]), str(row[1])

    # ── appends ─────────────────────────────────────────────────────

    def _build_row(
        self, env: EventEnvelope, *, seq: int, prev_hash: str
    ) -> SiteEvent:
        digest = event_hash(
            prev_hash,
            seq=seq,
            occurred_at=env.occurred_at,
            subject_type=env.subject_type,
            subject_id=env.subject_id,
            kind=env.kind,
            payload=env.payload,
            source=env.source,
            confidence=env.confidence,
            supersedes_event_id=env.supersedes_event_id,
        )
        return SiteEvent(
            id=str(uuid.uuid4()),
            org_id=env.org_id,
            project_id=env.project_id,
            seq=seq,
            occurred_at=env.occurred_at,
            recorded_at=_now(),
            subject_type=env.subject_type,
            subject_id=env.subject_id,
            kind=env.kind,
            payload=env.payload,
            source=env.source,
            confidence=env.confidence,
            evidence_ref=env.evidence_ref,
            status=env.status,
            supersedes_event_id=env.supersedes_event_id,
            actor_user_id=env.actor_user_id,
            prev_hash=prev_hash,
            hash=digest,
        )

    async def append(self, env: EventEnvelope) -> SiteEvent:
        rows = await self.append_many([env])
        return rows[0]

    async def append_many(self, envs: list[EventEnvelope]) -> list[SiteEvent]:
        """Append a batch in one chained run. All events must belong to the
        same stream `(org_id, project_id)` as the first envelope — the demo
        generator and drain loop both call per-stream."""
        if not envs:
            return []
        org_id = envs[0].org_id
        project_id = envs[0].project_id
        seq, prev_hash = await self._stream_head(org_id, project_id)
        out: list[SiteEvent] = []
        for env in envs:
            if env.org_id != org_id or env.project_id != project_id:
                raise ValueError(
                    "append_many requires every event in one (org, project) stream"
                )
            seq += 1
            row = self._build_row(env, seq=seq, prev_hash=prev_hash)
            self.db.add(row)
            prev_hash = row.hash
            out.append(row)
        await self.db.flush()
        return out

    # ── status transitions (append-only) ────────────────────────────

    async def set_status(
        self,
        event: SiteEvent,
        *,
        new_status: str,
        actor_user_id: str | None,
        reason: str | None = None,
        superseded_by_event_id: str | None = None,
    ) -> SiteEvent:
        """Record a status change as a companion event AND update the cached
        `status` column. Returns the companion event.

        `new_status` maps to one of the `event.confirmed/rejected/superseded`
        companion kinds. The companion event's subject is the target event,
        so the change is fully reconstructable from the log alone.
        """
        kind_map = {
            EventStatusValue.CONFIRMED: EventKind.EVENT_CONFIRMED.value,
            EventStatusValue.REJECTED: EventKind.EVENT_REJECTED.value,
            EventStatusValue.SUPERSEDED: EventKind.EVENT_SUPERSEDED.value,
        }
        kind = kind_map.get(new_status)
        if kind is None:
            raise ValueError(f"Unsupported status transition: {new_status!r}")
        payload: dict = {"target_seq": event.seq, "from_status": event.status}
        if reason:
            payload["reason"] = reason
        if superseded_by_event_id:
            payload["superseded_by_event_id"] = superseded_by_event_id
        companion = await self.append(
            EventEnvelope(
                org_id=event.org_id,
                project_id=event.project_id,
                subject_type=SubjectType.EVENT.value,
                subject_id=event.id,
                kind=kind,
                occurred_at=_now(),
                payload=payload,
                source="human" if actor_user_id else "system",
                confidence=1.0,
                status=EventStatusValue.CONFIRMED,
                actor_user_id=actor_user_id,
            )
        )
        event.status = new_status
        await self.db.flush()
        return companion

    # ── reads ───────────────────────────────────────────────────────

    async def get(self, org_id: str, event_id: str) -> SiteEvent | None:
        row = await self.db.get(SiteEvent, event_id)
        if row is None or row.org_id != org_id:
            return None
        return row

    async def query(
        self,
        org_id: str,
        project_id: str,
        *,
        subject_type: str | None = None,
        subject_id: str | None = None,
        kinds: list[str] | None = None,
        sources: list[str] | None = None,
        statuses: list[str] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        exclude_companion: bool = True,
        order: str = "asc",
        limit: int = 200,
        offset: int = 0,
    ) -> list[SiteEvent]:
        conditions = [
            SiteEvent.org_id == org_id,
            SiteEvent.project_id == project_id,
        ]
        if subject_type is not None:
            conditions.append(SiteEvent.subject_type == subject_type)
        if subject_id is not None:
            conditions.append(SiteEvent.subject_id == subject_id)
        if kinds:
            conditions.append(SiteEvent.kind.in_(kinds))
        if sources:
            conditions.append(SiteEvent.source.in_(sources))
        if statuses:
            conditions.append(SiteEvent.status.in_(statuses))
        if since is not None:
            conditions.append(SiteEvent.occurred_at >= since)
        if until is not None:
            conditions.append(SiteEvent.occurred_at <= until)
        if exclude_companion:
            conditions.append(SiteEvent.subject_type != SubjectType.EVENT.value)
        order_col = (
            SiteEvent.occurred_at.asc()
            if order == "asc"
            else SiteEvent.occurred_at.desc()
        )
        result = await self.db.execute(
            select(SiteEvent)
            .where(and_(*conditions))
            .order_by(order_col, SiteEvent.seq.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def all_for_stream(
        self, org_id: str, project_id: str
    ) -> list[SiteEvent]:
        result = await self.db.execute(
            select(SiteEvent)
            .where(
                SiteEvent.org_id == org_id,
                SiteEvent.project_id == project_id,
            )
            .order_by(SiteEvent.seq.asc())
        )
        return list(result.scalars().all())

    async def count_for_stream(self, org_id: str, project_id: str) -> int:
        rows = await self.all_for_stream(org_id, project_id)
        return len(rows)

    async def stream_is_empty(self, org_id: str, project_id: str) -> bool:
        """Cheap existence check (no full load)."""
        result = await self.db.execute(
            select(SiteEvent.id)
            .where(
                SiteEvent.org_id == org_id,
                SiteEvent.project_id == project_id,
            )
            .limit(1)
        )
        return result.first() is None

    # ── integrity ───────────────────────────────────────────────────

    async def verify_chain(self, org_id: str, project_id: str) -> dict:
        """Recompute the hash chain for a stream and report tampering.

        Returns `{ok, count, broken_at}` where `broken_at` is the `seq` of
        the first event whose stored hash or prev_hash doesn't match the
        recomputed value (None when intact)."""
        rows = await self.all_for_stream(org_id, project_id)
        prev_hash = ""
        expected_seq = 0
        for row in rows:
            expected_seq += 1
            recomputed = event_hash(
                prev_hash,
                seq=row.seq,
                occurred_at=row.occurred_at,
                subject_type=row.subject_type,
                subject_id=row.subject_id,
                kind=row.kind,
                payload=row.payload,
                source=row.source,
                confidence=row.confidence,
                supersedes_event_id=row.supersedes_event_id,
            )
            if (
                row.seq != expected_seq
                or row.prev_hash != prev_hash
                or row.hash != recomputed
            ):
                return {
                    "ok": False,
                    "count": len(rows),
                    "broken_at": row.seq,
                }
            prev_hash = row.hash
        return {"ok": True, "count": len(rows), "broken_at": None}

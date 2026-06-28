"""SQLAlchemy ORM models for auth + orgs.

Every UUID is `String(36)` to keep SQLite portable; every timestamp uses
`DateTime(timezone=True)` and is server-defaulted to `now()`. Roles +
plans + token kinds are stored as plain strings (with Python-side enums
defining the valid values) so migrations don't need DB-level enum types
that diverge between SQLite and Postgres.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"

    @classmethod
    def rank(cls, role: "Role | str") -> int:
        order = {cls.VIEWER: 0, cls.MEMBER: 1, cls.ADMIN: 2, cls.OWNER: 3}
        if isinstance(role, str):
            role = cls(role)
        return order[role]


class Plan(str, enum.Enum):
    TRIAL = "trial"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class TokenKind(str, enum.Enum):
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"
    MAGIC_LINK = "magic_link"


class EmailStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email_lower: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    email_display: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list["OrgMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default=Plan.TRIAL.value)
    # The PROJECT_TEMPLATES key the org's simulation engine should boot
    # with. Persists across backend restarts (the registry was per-app
    # before, so a restart reset every org to the default project).
    # Phase 1 added `active_project_version_id`; this column is kept as
    # the user-friendly slug ("westhafen") for compat with the existing
    # restore path. The registry resolves slug→version on boot.
    active_project_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # FK-ish: not a real FK because the project may belong to another
    # org (public templates) and we don't want cross-tenant FKs.
    active_project_version_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    memberships: Mapped[list["OrgMembership"]] = relationship(
        back_populates="org", cascade="all, delete-orphan"
    )


class OrgMembership(Base):
    __tablename__ = "org_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_org_memberships_user_id_org_id"),
        Index("ix_org_memberships_org_id", "org_id"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    user: Mapped[User] = relationship(back_populates="memberships")
    org: Mapped[Org] = relationship(back_populates="memberships")


class OrgInvite(Base):
    __tablename__ = "org_invites"
    __table_args__ = (
        Index("ix_org_invites_org_id", "org_id"),
        Index("ix_org_invites_email_lower", "email_lower"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    email_lower: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    invited_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    current_org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orgs.id", ondelete="SET NULL"), nullable=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class VerificationToken(Base):
    __tablename__ = "verification_tokens"
    __table_args__ = (
        Index("ix_verification_tokens_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=EmailStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ProjectVisibility(str, enum.Enum):
    PRIVATE = "private"            # only this org sees it
    ORG = "org"                    # shared within this org (same as private today)
    PUBLIC_TEMPLATE = "public_template"  # readable across orgs (used by stock seeds)


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    ARCHIVED = "archived"


class Project(Base):
    """Top-level project record.

    `current_version_id` is the mutable pointer at the immutable
    `project_versions` history. Engines load by version id so a "swap
    project for this org" is one atomic UPDATE on `orgs.active_project_id`
    or `orgs.active_project_version_id` (added below).
    """

    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_org_id", "org_id"),
        UniqueConstraint("org_id", "slug", name="uq_projects_org_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[str] = mapped_column(String(64), nullable=False, default="Residential")
    discipline: Mapped[str] = mapped_column(String(32), nullable=False, default="hochbau")
    visibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProjectVisibility.PRIVATE.value
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProjectStatus.DRAFT.value
    )
    current_version_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ProjectAsset(Base):
    """Binary blob attached to a project — currently only level
    background images (`kind = "level_background"`).

    Stored in-DB rather than on the filesystem so the org-delete cascade
    cleanly drops every blob and identical uploads dedupe naturally via
    `content_hash`. The `data` column is `LargeBinary` (BYTEA on
    Postgres, BLOB on SQLite) and is capped at 2 MB by the upload route.
    """

    __tablename__ = "project_assets"
    __table_args__ = (
        Index("ix_project_assets_project_id", "project_id"),
        Index("ix_project_assets_content_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class EventStatus(str, enum.Enum):
    """Lifecycle of a single ledger event.

    `confirmed` is ground truth (machine high-confidence or human-vouched).
    `proposed` is a low-confidence machine guess awaiting confirmation.
    `rejected` was dismissed by a human. `superseded` was replaced by a
    later correcting event. Status is a denormalised cache: every change
    is ALSO recorded as its own `event.confirmed/rejected/superseded`
    companion event so the append-only log stays the source of truth.
    """

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class EventSource(str, enum.Enum):
    """Provenance of a ledger event."""

    SIMULATION = "simulation"
    GENERATOR = "generator"
    HUMAN = "human"
    CAMERA = "camera"
    SENSOR = "sensor"
    INTEGRATION = "integration"
    SYSTEM = "system"


class SiteEvent(Base):
    """Append-only, hash-chained operational ledger entry.

    The system of record. Every action, material, worker and piece on the
    site becomes one immutable event. Current state and costs are folds
    over these rows; nothing is mutated except the denormalised `status`
    cache (whose every change is itself recorded as a companion event).

    Stream key is `(org_id, project_id)`. Within a stream, `seq` is a gap-
    free monotonic counter and `hash = sha256(prev_hash + canonical(core))`
    forms a tamper-evident chain. `occurred_at` is valid time (when it
    happened on site); `recorded_at` is system time (when we learned it),
    giving the ledger bitemporality for back-dated corrections.

    Source-agnostic by design: the simulation, the demo generator, manual
    capture, and a future camera `LiveSource` all append through the same
    `services.event_ledger.EventLedger`.
    """

    __tablename__ = "site_events"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "project_id", "seq", name="uq_site_events_stream_seq"
        ),
        Index(
            "ix_site_events_stream_occurred",
            "org_id",
            "project_id",
            "occurred_at",
        ),
        Index(
            "ix_site_events_stream_status",
            "org_id",
            "project_id",
            "status",
        ),
        Index("ix_site_events_subject", "subject_type", "subject_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    # Stream key within the org. Holds the engine's `project_id` (seed slug
    # or project uuid) so the ledger lines up with the active simulation
    # without a hard cross-tenant FK to `projects`.
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default=EventSource.SYSTEM.value
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EventStatus.CONFIRMED.value
    )
    supersedes_event_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ProjectVersion(Base):
    """Immutable snapshot of a ProjectDocument.

    The PK is the SHA-256 content hash of the canonical JSON, so two
    identical edits dedupe naturally. The `document` column stores the
    canonical JSON. Phase-1 implementation uses SQLAlchemy `JSON` for
    portability between SQLite and Postgres; in prod this lands as
    JSONB on Postgres automatically.
    """

    __tablename__ = "project_versions"
    __table_args__ = (
        Index("ix_project_versions_project_id_created_at", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

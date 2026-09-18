"""Core schema: User, ChannelIdentity, Permission (#8).

Design notes (see docs/ARCHITECTURE.md and CLAUDE.md for the full
rationale):

- A `User` is platform-independent. Each `ChannelIdentity` links one
  external account (a Telegram user id, an email address, a Matrix
  user id) on one channel to a `User`.
- `ChannelIdentity.external_id` is the lookup key the Auth Node
  queries by, so it must stay a plain, deterministic value — Fernet
  encryption is non-deterministic (a fresh nonce per call), so an
  encrypted column can never be looked up by equality. For Telegram
  and Matrix, the external id itself isn't the kind of sensitive data
  docs/ARCHITECTURE.md flags for encryption (a numeric Telegram id or
  a Matrix user id, not "raw email addresses ... or personal
  metadata"). For email, the lookup key is a SHA-256 hash of the
  lowercased address (see app.security.hashing), matching the
  `email_{email_hash}` thread_id scheme in docs/ARCHITECTURE.md — the
  raw address itself is only ever stored in the encrypted
  `raw_address` column, used solely to send SMTP replies.
- `Permission` is a separate table, not a `role` column, so it maps
  directly onto the Admin API's grant/revoke semantics (#24: POST/DELETE
  .../permissions) — granting is inserting a row, revoking is deleting
  one, with no separate "no permission" state to reconcile.
"""

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db.types import EncryptedString


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _db_enum(enum_cls: type[enum.Enum]) -> Enum:
    # SQLAlchemy's Enum stores the member NAME by default (e.g. "EMAIL").
    # These are (str, Enum) members whose value is the lowercase wire
    # format ("email") used throughout normalized events and .env — store
    # that instead, so the raw DB content matches what the rest of the
    # app (and anyone inspecting the DB file directly) actually expects.
    return Enum(enum_cls, native_enum=False, values_callable=lambda cls: [e.value for e in cls])


class Channel(enum.StrEnum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    MATRIX = "matrix"


class PermissionKind(enum.StrEnum):
    CHAT = "chat"
    ADMIN = "admin"


class Direction(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class RequestStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    channel_identities: Mapped[list["ChannelIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ChannelIdentity(Base):
    __tablename__ = "channel_identities"
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_channel_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    channel: Mapped[Channel] = mapped_column(_db_enum(Channel), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Only meaningful for the email channel — see module docstring.
    raw_address: Mapped[str | None] = mapped_column(EncryptedString, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="channel_identities")
    permissions: Mapped[list["Permission"]] = relationship(
        back_populates="channel_identity", cascade="all, delete-orphan"
    )


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("channel_identity_id", "kind", name="uq_channel_identity_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_identity_id: Mapped[int] = mapped_column(
        ForeignKey("channel_identities.id"), nullable=False
    )
    kind: Mapped[PermissionKind] = mapped_column(_db_enum(PermissionKind), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    channel_identity: Mapped["ChannelIdentity"] = relationship(back_populates="permissions")


class Agent(Base):
    """A User-owned, channel-agnostic autonomous agent (#37). Admin-editable
    — see app/admin/service.py — not only self-service by the owning user.
    """

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_agent_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ActionLog(Base):
    """Per-user, per-agent audit trail (#38)."""

    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    channel: Mapped[Channel] = mapped_column(_db_enum(Channel), nullable=False)
    direction: Mapped[Direction] = mapped_column(_db_enum(Direction), nullable=False)
    # Conversation content — same sensitivity class as ChannelIdentity.raw_address.
    text: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class AccessRequest(Base):
    """An unrecognized identity asking for access (#36) — created instead
    of only silently denying (see app/security/auth.py). Upserted, not
    inserted per message: one pending row per (channel, external_id).
    """

    __tablename__ = "access_requests"
    __table_args__ = (
        UniqueConstraint("channel", "external_id", name="uq_request_channel_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[Channel] = mapped_column(_db_enum(Channel), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    first_message_text: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        _db_enum(RequestStatus), nullable=False, default=RequestStatus.PENDING
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

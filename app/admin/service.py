"""Admin service layer (#35): the one place this logic lives. The
interactive CLI (#41) and the Admin API both call these functions —
neither re-implements the DB queries itself.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    AccessRequest,
    ActionLog,
    Agent,
    Channel,
    ChannelIdentity,
    Direction,
    Permission,
    PermissionKind,
    RequestStatus,
    User,
    _utcnow,
)
from app.db.session import sqlite_file_path
from app.security.auth import grant_permission

DEFAULT_AGENT_NAME = "default"


async def get_or_create_default_agent(session: AsyncSession, user_id: int) -> Agent:
    """A user's first Agent is created lazily, on first use — a
    single-agent user never has to think about agents at all (#37).
    """
    stmt = select(Agent).where(Agent.user_id == user_id, Agent.name == DEFAULT_AGENT_NAME)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    agent = Agent(user_id=user_id, name=DEFAULT_AGENT_NAME)
    session.add(agent)
    await session.flush()
    return agent


async def create_agent(session: AsyncSession, user_id: int, name: str) -> Agent:
    agent = Agent(user_id=user_id, name=name)
    session.add(agent)
    await session.flush()
    return agent


async def list_agents(session: AsyncSession, user_id: int) -> list[Agent]:
    stmt = select(Agent).where(Agent.user_id == user_id)
    return list((await session.execute(stmt)).scalars().all())


async def rename_agent(session: AsyncSession, agent_id: int, new_name: str) -> Agent:
    """Admin-editable (#37): callable against any user's Agent, not only
    the owning user's own — callers decide who's allowed to call this.
    """
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"No agent with id {agent_id}")
    agent.name = new_name
    await session.flush()
    return agent


async def set_agent_active(session: AsyncSession, agent_id: int, is_active: bool) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"No agent with id {agent_id}")
    agent.is_active = is_active
    await session.flush()
    return agent


async def record_action(
    session: AsyncSession,
    *,
    user_id: int,
    agent_id: int,
    channel: Channel,
    direction: Direction,
    text: str,
) -> ActionLog:
    entry = ActionLog(
        user_id=user_id, agent_id=agent_id, channel=channel, direction=direction, text=text
    )
    session.add(entry)
    await session.flush()
    return entry


async def request_access(
    session: AsyncSession, channel: Channel, external_id: str, message_text: str
) -> AccessRequest:
    """Upserts a pending request — one row per (channel, external_id),
    not one per message from a still-unresolved identity.
    """
    stmt = select(AccessRequest).where(
        AccessRequest.channel == channel,
        AccessRequest.external_id == external_id,
        AccessRequest.status == RequestStatus.PENDING,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    req = AccessRequest(channel=channel, external_id=external_id, first_message_text=message_text)
    session.add(req)
    await session.flush()
    return req


async def list_pending_requests(session: AsyncSession) -> list[AccessRequest]:
    stmt = select(AccessRequest).where(AccessRequest.status == RequestStatus.PENDING)
    return list((await session.execute(stmt)).scalars().all())


async def approve_request(session: AsyncSession, request_id: int) -> User:
    """Creates the User + ChannelIdentity + CHAT permission in one step —
    an admin doesn't separately create the user then grant access.
    """
    request = await session.get(AccessRequest, request_id)
    if request is None or request.status != RequestStatus.PENDING:
        raise ValueError(f"No pending request with id {request_id}")

    user = User(display_name=f"Approved from {request.channel.value} request")
    session.add(user)
    await session.flush()
    identity = ChannelIdentity(
        user_id=user.id, channel=request.channel, external_id=request.external_id
    )
    session.add(identity)
    await session.flush()
    await grant_permission(session, identity, PermissionKind.CHAT)

    request.status = RequestStatus.APPROVED
    request.resolved_at = _utcnow()
    await session.flush()
    return user


async def deny_request(session: AsyncSession, request_id: int) -> None:
    request = await session.get(AccessRequest, request_id)
    if request is None or request.status != RequestStatus.PENDING:
        raise ValueError(f"No pending request with id {request_id}")
    request.status = RequestStatus.DENIED
    request.resolved_at = _utcnow()
    await session.flush()


LOG_SEARCH_MAX_LIMIT = 500
_LOG_SEARCH_BATCH = 500


def _as_utc(value: datetime) -> datetime:
    """The database stores UTC. A naive datetime is taken as UTC, an aware
    one is converted, so a caller in another timezone gets the window it
    meant instead of a silently shifted one.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def search_action_logs(
    session: AsyncSession,
    *,
    user_id: int | None = None,
    agent_id: int | None = None,
    channel: Channel | None = None,
    direction: Direction | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    keyword: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ActionLog]:
    """Search the audit trail (#39). Every filter is optional and they
    combine with AND. Results are most recent first (by insertion order).

    `since` is inclusive and `until` exclusive, so consecutive windows
    never overlap. `offset` skips that many *matching* rows, for paging.

    `keyword` is a case-insensitive substring match against the
    *decrypted* text. The text column holds Fernet ciphertext, which is
    different on every write, so it cannot be searched or compared in SQL:
    every other filter runs in SQL, then the keyword is applied in Python
    to each candidate row, newest first, stopping as soon as `limit`
    matches are found. That is O(n) in the number of rows passing the
    other filters, which is fine for a single-user to small-group local
    assistant. Narrow with user, agent, channel or dates first on a large
    log. No index or search infrastructure is built on purpose.
    """
    if not 1 <= limit <= LOG_SEARCH_MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {LOG_SEARCH_MAX_LIMIT}, got {limit}")
    if offset < 0:
        raise ValueError(f"offset must be 0 or more, got {offset}")

    stmt = select(ActionLog)
    if user_id is not None:
        stmt = stmt.where(ActionLog.user_id == user_id)
    if agent_id is not None:
        stmt = stmt.where(ActionLog.agent_id == agent_id)
    if channel is not None:
        stmt = stmt.where(ActionLog.channel == channel)
    if direction is not None:
        stmt = stmt.where(ActionLog.direction == direction)
    if since is not None:
        stmt = stmt.where(ActionLog.created_at >= _as_utc(since))
    if until is not None:
        stmt = stmt.where(ActionLog.created_at < _as_utc(until))
    stmt = stmt.order_by(ActionLog.id.desc())

    needle = keyword.strip().lower() if keyword else ""
    if not needle:
        return list((await session.execute(stmt.limit(limit).offset(offset))).scalars().all())

    matches: list[ActionLog] = []
    skipped = 0
    last_id: int | None = None
    while len(matches) < limit:
        batch_stmt = stmt if last_id is None else stmt.where(ActionLog.id < last_id)
        batch = list(
            (await session.execute(batch_stmt.limit(_LOG_SEARCH_BATCH))).scalars().all()
        )
        for entry in batch:
            if needle not in entry.text.lower():
                continue
            if skipped < offset:
                skipped += 1
                continue
            matches.append(entry)
            if len(matches) == limit:
                break
        if len(batch) < _LOG_SEARCH_BATCH:
            break
        last_id = batch[-1].id
    return matches


@dataclass(frozen=True)
class StorageOverview:
    """Numbers about what the database holds (#40)."""

    db_size_bytes: int | None  # None when the database is not a SQLite file
    row_counts: dict[str, int]  # table name -> number of rows
    oldest_log_at: datetime | None  # UTC, None when there is no action log yet
    newest_log_at: datetime | None


_COUNTED_MODELS = (User, ChannelIdentity, Permission, AccessRequest, Agent, ActionLog)


async def storage_overview(session: AsyncSession) -> StorageOverview:
    """Basic visibility for the admin (#40): the size of the SQLite file,
    the row count of every table, and the time span the audit trail
    covers. Not a storage engine or a backup tool, just numbers.

    The size is that of the main database file only. Row counts are exact
    `COUNT(*)` queries, not estimates.
    """
    counts = {
        model.__tablename__: (
            await session.execute(select(func.count()).select_from(model))
        ).scalar_one()
        for model in _COUNTED_MODELS
    }
    span = select(func.min(ActionLog.created_at), func.max(ActionLog.created_at))
    oldest, newest = (await session.execute(span)).one()

    path = sqlite_file_path(get_settings().database_url)
    size = path.stat().st_size if path is not None and path.exists() else None
    return StorageOverview(
        db_size_bytes=size,
        row_counts=counts,
        oldest_log_at=_as_utc(oldest) if oldest is not None else None,
        newest_log_at=_as_utc(newest) if newest is not None else None,
    )

"""Admin service layer (#35): the one place this logic lives. The
interactive CLI (#41) and the Admin API both call these functions —
neither re-implements the DB queries itself.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AccessRequest,
    ActionLog,
    Channel,
    ChannelIdentity,
    Direction,
    PermissionKind,
    RequestStatus,
    User,
    _utcnow,
)
from app.security.auth import grant_permission


async def record_action(
    session: AsyncSession,
    *,
    user_id: int,
    channel: Channel,
    direction: Direction,
    text: str,
    agent_id: int | None = None,
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

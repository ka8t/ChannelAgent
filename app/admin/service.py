"""Admin service layer (#35): the one place this logic lives. The
interactive CLI (#41) and the Admin API both call these functions —
neither re-implements the DB queries itself.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AccessRequest,
    ActionLog,
    Agent,
    Channel,
    ChannelIdentity,
    Direction,
    PermissionKind,
    RequestStatus,
    User,
    _utcnow,
)
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

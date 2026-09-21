"""Admin API routes. Every route is covered by the app-level API_SERVER_KEY
dependency (see app/api/app.py), and none holds business logic: each calls
the same app.admin.service function the admin console calls (#35's
one-service-layer rule). Service errors become HTTP statuses in one place,
the exception handlers of app/api/app.py: NotFoundError 404, ConflictError
409, InvalidInputError 422.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.api.deps import get_db_session
from app.api.schemas import (
    AccessRequestOut,
    ActionLogOut,
    AdminEventOut,
    AgentCreate,
    AgentOut,
    AgentUpdate,
    ChannelIdentityCreate,
    ChannelIdentityOut,
    ConversationResetOut,
    IdentityAgentSet,
    PermissionGrant,
    PermissionOut,
    StorageOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.api.scopes import Scope, require
from app.db.models import (
    ActionLog,
    ActionStatus,
    AdminEvent,
    Agent,
    Channel,
    ChannelIdentity,
    Direction,
    PermissionKind,
    RequestStatus,
    User,
)

router = APIRouter()

API_ACTOR = "api"


# --- Users ---


@router.post(
    "/users",
    dependencies=[require(Scope.OPERATE)],
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    body: UserCreate, session: AsyncSession = Depends(get_db_session)
) -> User:
    user = await service.create_user(session, body.display_name, actor=API_ACTOR)
    await session.commit()
    return user


@router.get("/users", dependencies=[require(Scope.READ)], response_model=list[UserOut])
async def list_users(session: AsyncSession = Depends(get_db_session)) -> list[User]:
    return await service.list_users(session)


@router.get("/users/{user_id}", dependencies=[require(Scope.READ)], response_model=UserOut)
async def get_user(user_id: int, session: AsyncSession = Depends(get_db_session)) -> User:
    return await service.get_user(session, user_id)


@router.patch("/users/{user_id}", dependencies=[require(Scope.OPERATE)], response_model=UserOut)
async def update_user(
    user_id: int, body: UserUpdate, session: AsyncSession = Depends(get_db_session)
) -> User:
    user = await service.update_user(
        session,
        user_id,
        display_name=body.display_name,
        is_active=body.is_active,
        actor=API_ACTOR,
    )
    await session.commit()
    return user


@router.delete(
    "/users/{user_id}",
    dependencies=[require(Scope.OWNER)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user(
    user_id: int,
    purge: bool = Query(
        default=False, description="Also delete the user's agents, audit trail and conversations."
    ),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await service.delete_user(session, user_id, purge=purge, actor=API_ACTOR)
    await session.commit()


# --- Channel identities ---


@router.post(
    "/users/{user_id}/channels", dependencies=[require(Scope.OPERATE)],
    response_model=ChannelIdentityOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_channel_identity(
    user_id: int, body: ChannelIdentityCreate, session: AsyncSession = Depends(get_db_session)
) -> ChannelIdentity:
    identity = await service.add_channel_identity(
        session, user_id, body.channel, body.identifier, actor=API_ACTOR
    )
    await session.commit()
    return identity


@router.get(
    "/users/{user_id}/channels",
    dependencies=[require(Scope.READ)],
    response_model=list[ChannelIdentityOut],
)
async def list_channel_identities(
    user_id: int, session: AsyncSession = Depends(get_db_session)
) -> list[ChannelIdentity]:
    return await service.list_channel_identities(session, user_id)


@router.delete(
    "/users/{user_id}/channels/{channel_identity_id}",
    dependencies=[require(Scope.OPERATE)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_channel_identity(
    user_id: int, channel_identity_id: int, session: AsyncSession = Depends(get_db_session)
) -> None:
    await service.remove_channel_identity(
        session, user_id, channel_identity_id, actor=API_ACTOR
    )
    await session.commit()


@router.put(
    "/users/{user_id}/channels/{channel_identity_id}/agent",
    dependencies=[require(Scope.OPERATE)],
    response_model=ChannelIdentityOut,
)
async def set_identity_agent(
    user_id: int,
    channel_identity_id: int,
    body: IdentityAgentSet,
    session: AsyncSession = Depends(get_db_session),
) -> ChannelIdentity:
    """Choose which of the user's agents this channel identity talks to (#54)."""
    identity = await service.set_identity_agent(
        session, user_id, channel_identity_id, body.agent_id, actor=API_ACTOR
    )
    await session.commit()
    return identity


# --- Conversations (#63) ---


@router.post(
    "/users/{user_id}/conversations/reset",
    dependencies=[require(Scope.OPERATE)],
    response_model=ConversationResetOut,
)
async def reset_conversation(
    user_id: int,
    agent_id: int | None = Query(
        default=None, description="Only this agent's conversation. Omit for all of them."
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationResetOut:
    """Forget the stored history of a conversation that cannot be read. The
    next message starts a fresh one; the audit trail is kept.
    """
    threads = await service.reset_conversation(session, user_id, agent_id, actor=API_ACTOR)
    await session.commit()
    return ConversationResetOut(threads_reset=threads)


# --- Permissions ---


@router.post(
    "/users/{user_id}/channels/{channel_identity_id}/permissions",
    dependencies=[require(Scope.ADMIN)],
    response_model=PermissionOut,
    status_code=status.HTTP_201_CREATED,
)
async def grant(
    user_id: int,
    channel_identity_id: int,
    body: PermissionGrant,
    session: AsyncSession = Depends(get_db_session),
) -> PermissionOut:
    permission = await service.grant_identity_permission(
        session, user_id, channel_identity_id, body.kind, actor=API_ACTOR
    )
    await session.commit()
    return PermissionOut.model_validate(permission)


@router.get(
    "/users/{user_id}/channels/{channel_identity_id}/permissions",
    dependencies=[require(Scope.READ)],
    response_model=list[PermissionOut],
)
async def list_permissions(
    user_id: int, channel_identity_id: int, session: AsyncSession = Depends(get_db_session)
) -> list[PermissionOut]:
    permissions = await service.list_identity_permissions(session, user_id, channel_identity_id)
    return [PermissionOut.model_validate(p) for p in permissions]


@router.delete(
    "/users/{user_id}/channels/{channel_identity_id}/permissions/{kind}",
    dependencies=[require(Scope.ADMIN)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke(
    user_id: int,
    channel_identity_id: int,
    kind: PermissionKind,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await service.revoke_identity_permission(
        session, user_id, channel_identity_id, kind, actor=API_ACTOR
    )
    await session.commit()


# --- Access requests (#36) ---


@router.get("/requests", dependencies=[require(Scope.READ)], response_model=list[AccessRequestOut])
async def list_requests(
    status_filter: str = Query(
        default="pending", alias="status", pattern="^(pending|approved|denied|all)$"
    ),
    session: AsyncSession = Depends(get_db_session),
):
    wanted = None if status_filter == "all" else RequestStatus(status_filter)
    return await service.list_requests(session, wanted)


@router.post(
    "/requests/{request_id}/approve",
    dependencies=[require(Scope.OPERATE)],
    response_model=UserOut,
)
async def approve_request(request_id: int, session: AsyncSession = Depends(get_db_session)) -> User:
    user = await service.approve_request(session, request_id, resolved_by=API_ACTOR)
    await session.commit()
    return user


@router.post(
    "/requests/{request_id}/deny",
    dependencies=[require(Scope.OPERATE)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def deny_request(request_id: int, session: AsyncSession = Depends(get_db_session)) -> None:
    await service.deny_request(session, request_id, resolved_by=API_ACTOR)
    await session.commit()


# --- Agents (#37): an admin can edit any user's agent ---


@router.get(
    "/users/{user_id}/agents",
    dependencies=[require(Scope.READ)],
    response_model=list[AgentOut],
)
async def list_agents(user_id: int, session: AsyncSession = Depends(get_db_session)) -> list[Agent]:
    return await service.list_agents(session, user_id)


@router.post(
    "/users/{user_id}/agents",
    dependencies=[require(Scope.OPERATE)],
    response_model=AgentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    user_id: int, body: AgentCreate, session: AsyncSession = Depends(get_db_session)
) -> Agent:
    agent = await service.create_agent(session, user_id, body.name, actor=API_ACTOR)
    await session.commit()
    return agent


@router.get("/agents/{agent_id}", dependencies=[require(Scope.READ)], response_model=AgentOut)
async def get_agent(agent_id: int, session: AsyncSession = Depends(get_db_session)) -> Agent:
    return await service.get_agent(session, agent_id)


@router.patch("/agents/{agent_id}", dependencies=[require(Scope.OPERATE)], response_model=AgentOut)
async def update_agent(
    agent_id: int, body: AgentUpdate, session: AsyncSession = Depends(get_db_session)
) -> Agent:
    """Rename and/or activate or deactivate, whoever owns the agent."""
    agent = await service.get_agent(session, agent_id)
    if body.name is not None:
        agent = await service.rename_agent(session, agent_id, body.name, actor=API_ACTOR)
    if body.is_active is not None:
        agent = await service.set_agent_active(
            session, agent_id, body.is_active, actor=API_ACTOR
        )
    await session.commit()
    return agent


# --- Audit trail search (#39) ---


@router.get("/logs", dependencies=[require(Scope.ADMIN)], response_model=list[ActionLogOut])
async def search_logs(
    user_id: int | None = None,
    agent_id: int | None = None,
    channel: Channel | None = None,
    direction: Direction | None = None,
    status: ActionStatus | None = None,
    since: datetime | None = Query(default=None, description="Inclusive. Naive = UTC."),
    until: datetime | None = Query(default=None, description="Exclusive. Naive = UTC."),
    keyword: str | None = Query(default=None, description="Case-insensitive, on decrypted text."),
    limit: int = Query(default=100, ge=1, le=service.LOG_SEARCH_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[ActionLog]:
    logs = await service.search_action_logs(
        session,
        actor=API_ACTOR,
        user_id=user_id,
        agent_id=agent_id,
        channel=channel,
        direction=direction,
        status=status,
        since=since,
        until=until,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    await session.commit()  # a read of decrypted logs is itself recorded (#59)
    return logs


# --- What administrators did (#59) ---


@router.get(
    "/admin-events",
    dependencies=[require(Scope.ADMIN)],
    response_model=list[AdminEventOut],
)
async def search_admin_events(
    actor: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    since: datetime | None = Query(default=None, description="Inclusive. Naive = UTC."),
    until: datetime | None = Query(default=None, description="Exclusive. Naive = UTC."),
    limit: int = Query(default=100, ge=1, le=service.LOG_SEARCH_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[AdminEvent]:
    events = await service.search_admin_events(
        session,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
        reader=API_ACTOR,
    )
    await session.commit()
    return events


# --- Storage overview (#40) ---


@router.get("/storage", dependencies=[require(Scope.READ)], response_model=StorageOut)
async def storage(session: AsyncSession = Depends(get_db_session)) -> StorageOut:
    overview = await service.storage_overview(session)
    return StorageOut(
        db_size_bytes=overview.db_size_bytes,
        row_counts=overview.row_counts,
        oldest_log_at=overview.oldest_log_at,
        newest_log_at=overview.newest_log_at,
        undecryptable_rows=overview.undecryptable_rows,
        undecryptable_by_table=overview.undecryptable_by_table,
        checkpoint_size_bytes=overview.checkpoint_size_bytes,
        checkpoint_row_counts=overview.checkpoint_row_counts,
    )

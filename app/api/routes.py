"""Admin API routes (#23, #24): CRUD for users and their channel
identities, and grant/revoke for permissions. Every route here is
already covered by the app-level API_SERVER_KEY dependency (see
app/api/app.py) — nothing in this file re-checks auth.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db_session
from app.api.schemas import (
    ChannelIdentityCreate,
    ChannelIdentityOut,
    PermissionGrant,
    PermissionOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.db.models import Channel, ChannelIdentity, PermissionKind, User
from app.security.auth import grant_permission, revoke_permission
from app.security.hashing import channel_identifier_key

router = APIRouter()


async def _get_user_or_404(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user with id {user_id}")
    return user


async def _get_channel_identity_or_404(
    session: AsyncSession, user_id: int, channel_identity_id: int
) -> ChannelIdentity:
    identity = await session.get(ChannelIdentity, channel_identity_id)
    if identity is None or identity.user_id != user_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No channel identity {channel_identity_id} for user {user_id}",
        )
    return identity


# --- Users ---


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, session: AsyncSession = Depends(get_db_session)
) -> User:
    user = User(display_name=body.display_name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
async def list_users(session: AsyncSession = Depends(get_db_session)) -> list[User]:
    return list((await session.execute(select(User))).scalars().all())


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int, session: AsyncSession = Depends(get_db_session)) -> User:
    return await _get_user_or_404(session, user_id)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, body: UserUpdate, session: AsyncSession = Depends(get_db_session)
) -> User:
    user = await _get_user_or_404(session, user_id)
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.is_active is not None:
        user.is_active = body.is_active
    await session.commit()
    await session.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, session: AsyncSession = Depends(get_db_session)) -> None:
    user = await _get_user_or_404(session, user_id)
    await session.delete(user)  # cascades to channel_identities and permissions
    await session.commit()


# --- Channel identities ---


@router.post(
    "/users/{user_id}/channels",
    response_model=ChannelIdentityOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_channel_identity(
    user_id: int, body: ChannelIdentityCreate, session: AsyncSession = Depends(get_db_session)
) -> ChannelIdentity:
    await _get_user_or_404(session, user_id)
    external_id = channel_identifier_key(body.channel, body.identifier)
    raw_address = body.identifier if body.channel is Channel.EMAIL else None
    identity = ChannelIdentity(
        user_id=user_id, channel=body.channel, external_id=external_id, raw_address=raw_address
    )
    session.add(identity)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This channel identity is already linked to a user"
        ) from exc
    await session.refresh(identity)
    return identity


@router.get("/users/{user_id}/channels", response_model=list[ChannelIdentityOut])
async def list_channel_identities(
    user_id: int, session: AsyncSession = Depends(get_db_session)
) -> list[ChannelIdentity]:
    await _get_user_or_404(session, user_id)
    stmt = select(ChannelIdentity).where(ChannelIdentity.user_id == user_id)
    return list((await session.execute(stmt)).scalars().all())


@router.delete("/users/{user_id}/channels/{channel_identity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_identity(
    user_id: int, channel_identity_id: int, session: AsyncSession = Depends(get_db_session)
) -> None:
    identity = await _get_channel_identity_or_404(session, user_id, channel_identity_id)
    await session.delete(identity)
    await session.commit()


# --- Permissions ---


@router.post(
    "/users/{user_id}/channels/{channel_identity_id}/permissions",
    response_model=PermissionOut,
    status_code=status.HTTP_201_CREATED,
)
async def grant(
    user_id: int,
    channel_identity_id: int,
    body: PermissionGrant,
    session: AsyncSession = Depends(get_db_session),
) -> PermissionOut:
    identity = await _get_channel_identity_or_404(session, user_id, channel_identity_id)
    permission = await grant_permission(session, identity, body.kind)
    await session.commit()
    return PermissionOut.model_validate(permission)


@router.get("/users/{user_id}/channels/{channel_identity_id}/permissions", response_model=list[PermissionOut])
async def list_permissions(
    user_id: int, channel_identity_id: int, session: AsyncSession = Depends(get_db_session)
) -> list[PermissionOut]:
    identity = await _get_channel_identity_or_404(session, user_id, channel_identity_id)
    stmt = select(ChannelIdentity).where(ChannelIdentity.id == identity.id).options(
        selectinload(ChannelIdentity.permissions)
    )
    identity = (await session.execute(stmt)).scalar_one()
    return [PermissionOut.model_validate(p) for p in identity.permissions]


@router.delete(
    "/users/{user_id}/channels/{channel_identity_id}/permissions/{kind}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke(
    user_id: int,
    channel_identity_id: int,
    kind: PermissionKind,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    identity = await _get_channel_identity_or_404(session, user_id, channel_identity_id)
    revoked = await revoke_permission(session, identity, kind)
    if not revoked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Permission {kind} was not held")
    await session.commit()

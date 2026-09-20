"""Request/response models for the Admin API.

raw_address (email) is never returned by any of these — see
ChannelIdentityOut. external_id is safe to return for every channel:
for Telegram/Matrix it's just the platform's own id, and for email
it's a one-way hash (app.security.hashing.hash_email), not the address
itself.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import Channel, Direction, PermissionKind


class UserCreate(BaseModel):
    display_name: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_name: str | None
    is_active: bool


class ChannelIdentityCreate(BaseModel):
    channel: Channel
    # Raw as an admin would naturally provide it: a Telegram numeric id,
    # a Matrix user id, or — for channel="email" — the actual address.
    # The route computes external_id (and, for email, encrypts the
    # address into raw_address) from this; callers never construct the
    # stored key themselves.
    identifier: str


class ChannelIdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    channel: Channel
    external_id: str


class PermissionGrant(BaseModel):
    kind: PermissionKind


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: PermissionKind


class ActionLogOut(BaseModel):
    """One audit-trail entry (#39). `text` is the decrypted message, so
    this is only ever served behind the API_SERVER_KEY dependency.
    """

    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    agent_id: int
    channel: Channel
    direction: Direction
    text: str
    created_at: datetime


class StorageOut(BaseModel):
    """What the database holds (#40). The file path is left out on purpose:
    the admin needs the size, not the server's directory layout.
    """

    db_size_bytes: int | None
    row_counts: dict[str, int]
    oldest_log_at: datetime | None
    newest_log_at: datetime | None

"""Request/response models for the Admin API.

raw_address (email) is never returned by any of these — see
ChannelIdentityOut. external_id is safe to return for every channel:
for Telegram/Matrix it's just the platform's own id, and for email
it's a one-way hash (app.security.hashing.hash_email), not the address
itself.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ActionStatus, Channel, Direction, PermissionKind, RequestStatus


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_name: str | None
    is_active: bool


class ChannelIdentityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    active_agent_id: int | None = None


class IdentityAgentSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """`agent_id: null` goes back to the user's default agent."""

    agent_id: int | None


class PermissionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    status: ActionStatus
    text: str
    created_at: datetime


class AdminEventOut(BaseModel):
    """One administrator action (#59). `details` is decrypted JSON text."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    actor: str
    action: str
    target_type: str
    target_id: int | None
    details: str | None


class ConversationResetOut(BaseModel):
    threads_reset: int


class StorageOut(BaseModel):
    """What the database holds (#40). The file path is left out on purpose:
    the admin needs the size, not the server's directory layout.
    """

    db_size_bytes: int | None
    row_counts: dict[str, int]
    oldest_log_at: datetime | None
    newest_log_at: datetime | None
    undecryptable_rows: int
    undecryptable_by_table: dict[str, int]
    checkpoint_size_bytes: int | None = None
    checkpoint_row_counts: dict[str, int] = {}


MemoryMode = Literal["off", "ondemand", "always", "search"]


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    # The per-agent configuration (#110); only what is given is set, the rest keeps its default.
    system_prompt: str | None = Field(default=None, max_length=20000)
    model: str | None = Field(default=None, max_length=200)
    memory_mode: MemoryMode = "off"
    tools: list[str] = Field(default_factory=list, max_length=100)


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Only the fields that are given change."""

    name: str | None = None
    is_active: bool | None = None
    # `null` clears the prompt and the model; leave a setting out to keep it (#110).
    system_prompt: str | None = Field(default=None, max_length=20000)
    model: str | None = Field(default=None, max_length=200)
    memory_mode: MemoryMode | None = None
    tools: list[str] | None = Field(default=None, max_length=100)


class AgentOut(BaseModel):
    """The system prompt is only returned to an administrator: everyone else sees
    `has_system_prompt`. The other settings are names and switches."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    name: str
    is_active: bool
    system_prompt: str | None = None
    has_system_prompt: bool = False
    model: str | None = None
    memory_mode: str = "off"
    tools: list[str] = []

class AccessRequestOut(BaseModel):
    """`first_message_text` is the decrypted first message of the unknown
    sender, so this is only served behind the API_SERVER_KEY dependency.
    """

    model_config = ConfigDict(from_attributes=True)
    id: int
    channel: Channel
    external_id: str
    first_message_text: str
    status: RequestStatus
    requested_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None


class WhoAmIOut(BaseModel):
    actor: str
    scope: str
    api_version: str


class ComponentStatus(BaseModel):
    healthy: bool
    seconds_since_success: float


class DatabaseStatus(BaseModel):
    kind: str
    revision: str | None
    size_bytes: int | None


class EngineStatus(BaseModel):
    reachable: bool
    model: str | None = None
    n_ctx: int | None = None


class StatusOut(BaseModel):
    api_version: str
    started_at: datetime
    uptime_seconds: int
    components: dict[str, ComponentStatus]
    database: DatabaseStatus
    engine: EngineStatus


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    status: str
    progress: float | None
    message: str | None
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class BackupOut(BaseModel):
    name: str
    kind: str
    size_bytes: int
    created_at: datetime | None


class ConfigEntryOut(BaseModel):
    """One variable. The value of a secret is never returned: `value` is null and
    `is_set` says whether one is in place.
    """

    key: str
    value: str | None
    is_set: bool
    secret: bool


class ConfigSetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    value: str


class ConfigSetOut(BaseModel):
    """What changed, never the value."""

    key: str
    changed: bool
    backup: str
    applies: str


class ModelOut(BaseModel):
    name: str
    size_bytes: int
    sha256: str | None
    modified_at: datetime
    loaded: bool
    configured: bool


class RoutingRuleIn(BaseModel):
    """One rule of the routing table (#105): match_value is an integer for
    min_length, a string for command_prefix — validated by app.admin.routing
    against match_type, since the two share no single Pydantic type.
    """

    model_config = ConfigDict(extra="forbid")
    match_type: str
    match_value: int | str
    model: str


class RoutingRuleOut(BaseModel):
    match_type: str
    match_value: str
    model: str


class RoutingIn(BaseModel):
    """Replaces the whole routing table (PUT semantics): a field left out clears
    to its empty default rather than staying unchanged, since a partial ordered
    list has no obvious meaning to merge.
    """

    model_config = ConfigDict(extra="forbid")
    default_model: str | None = Field(default=None, max_length=200)
    rules: list[RoutingRuleIn] = Field(default_factory=list, max_length=50)
    model_ctx_sizes: dict[str, int] = Field(default_factory=dict)


class RoutingOut(BaseModel):
    default_model: str | None
    rules: list[RoutingRuleOut]
    model_ctx_sizes: dict[str, int]


class ModelImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    name: str | None = None
    force: bool = False


class ModelPullIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: str
    name: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-fA-F]{64}$")
    force: bool = False

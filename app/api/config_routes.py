"""The configuration in `.env` (#109): the same reading and writing `./start.sh --show-config`
and `./start.sh --set` use (`app/settings_rules.py`), so the script and the API cannot
disagree. A secret is never returned and never echoed; ENCRYPTION_KEY is never set here.

`.env` belongs to the host, not to a container: where there is none (the application in
its container) the routes answer 409 and the host operation is served by the host helper.
"""

import os

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_rules as rules
from app.admin import service
from app.api.actor import current_actor
from app.api.deps import get_db_session
from app.api.errors import error_responses
from app.api.schemas import ConfigEntryOut, ConfigSetIn, ConfigSetOut
from app.api.scopes import Scope, require

router = APIRouter()


def _files() -> tuple[str, str]:
    env = os.environ.get("ENV_FILE", ".env")
    example = os.environ.get("ENV_EXAMPLE_FILE", ".env.example")
    if not os.path.isfile(env) or not os.path.isfile(example):
        raise service.ConflictError(
            "There is no .env file here: the configuration is edited on the host "
            "(./start.sh --show-config, ./start.sh --set)"
        )
    return env, example


@router.get(
    "/config",
    dependencies=[require(Scope.ADMIN)],
    response_model=list[ConfigEntryOut],
    tags=["config"],
    responses=error_responses(409),
)
async def get_config() -> list[ConfigEntryOut]:
    """Every variable of `.env.example` with its value in `.env`; a secret has no value."""
    env, example = _files()
    return [
        ConfigEntryOut(
            key=e["key"],
            value=None if e["secret"] else (e["value"] or None),
            is_set=e["is_set"],
            secret=e["secret"],
        )
        for e in rules.config_entries(env, example)
    ]


@router.patch(
    "/config",
    dependencies=[require(Scope.OWNER)],
    response_model=ConfigSetOut,
    tags=["config"],
    responses=error_responses(409),
)
async def set_config(
    body: ConfigSetIn, session: AsyncSession = Depends(get_db_session)
) -> ConfigSetOut:
    """Set one variable after the same checks as `./start.sh --set`. It applies at the next
    start. `ENCRYPTION_KEY` is refused (409): only the rekey job changes it.
    """
    env, example = _files()
    try:
        result = rules.set_config(env, example, body.key, body.value, allow_initial_key=False)
    except rules.ConfigError as exc:
        if exc.kind == "key_protected":
            raise service.ConflictError(str(exc)) from None
        raise service.InvalidInputError(str(exc)) from None
    await service.record_admin_event(
        session,
        actor=current_actor(),
        action="config.set",
        target_type="config",
        details={"key": body.key},
    )
    await session.commit()
    return ConfigSetOut(
        key=body.key,
        changed=True,
        backup=result["backup"],
        applies="at the next start of the application",
    )

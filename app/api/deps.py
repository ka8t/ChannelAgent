"""Shared FastAPI dependencies for the Admin API: a DB session per
request, and the API_SERVER_KEY bearer-auth check (#22).
"""

import logging
import secrets
import time
from collections import deque
from collections.abc import AsyncIterator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.actor import actor_from_header, set_actor
from app.api.scopes import Principal, Scope
from app.config import get_settings
from app.db.session import get_sessionmaker

# The key rule lives in app.settings_rules, which `./start.sh --set` also runs (#75):
# the API and the command that writes the key can never disagree.
from app.settings_rules import MIN_API_KEY_LENGTH, api_key_is_acceptable  # noqa: F401

logger = logging.getLogger("channelagent.api")

# Failed-attempt limiter (#58): at most FAILURE_LIMIT failures per source
# address inside FAILURE_WINDOW_SECONDS, then 429 for everything from that
# address (a right key included, otherwise a guesser learns nothing from
# being blocked but keeps guessing). In memory on purpose: a restart
# clears it, and one process serves the API.
FAILURE_LIMIT = 10
FAILURE_WINDOW_SECONDS = 60
MAX_TRACKED_ADDRESSES = 1024
_failures: dict[str, deque[float]] = {}


def _now() -> float:
    return time.monotonic()


def reset_failure_state() -> None:
    _failures.clear()


def _source(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _recent_failures(address: str, now: float) -> deque[float]:
    window = _failures.get(address)
    if window is None:
        return deque()
    while window and now - window[0] > FAILURE_WINDOW_SECONDS:
        window.popleft()
    if not window:
        del _failures[address]
        return deque()
    return window


def _record_failure(address: str, now: float) -> None:
    window = _recent_failures(address, now)
    window.append(now)
    _failures[address] = window
    while len(_failures) > MAX_TRACKED_ADDRESSES:
        del _failures[next(iter(_failures))]


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def verify_api_key(
    request: Request, authorization: str | None = Header(default=None)
) -> None:
    """Applied to every route via the app-level `dependencies=` list in
    app/api/app.py, not per-router — a new endpoint added later can't
    accidentally ship without this check.
    """
    settings = get_settings()
    if not settings.api_server_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "API_SERVER_KEY is not configured"
        )
    address = _source(request)
    now = _now()
    if len(_recent_failures(address, now)) >= FAILURE_LIMIT:
        logger.warning("Admin API: request from %s blocked, too many failed attempts.", address)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts, try again later"
        )
    expected = f"Bearer {settings.api_server_key}"
    # Constant-time comparison — this guards a real secret, not just a
    # display value, so a naive `==` (early-exit on first mismatched
    # byte) would leak timing information about how many leading
    # characters of the token a guess got right.
    if authorization is None or not secrets.compare_digest(authorization, expected):
        _record_failure(address, now)
        logger.warning("Admin API: failed authentication from %s.", address)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")
    # One shared key, no named administrators yet (deferred): the key holder is the owner.
    actor = actor_from_header(request.headers.get("x-client"))
    set_actor(actor)
    request.state.principal = Principal(actor=actor, scope=Scope.OWNER)

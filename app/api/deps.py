"""Shared FastAPI dependencies for the Admin API: a DB session per
request, and the API_SERVER_KEY bearer-auth check (#22).
"""

import secrets
from collections.abc import AsyncIterator

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_sessionmaker


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def verify_api_key(authorization: str | None = Header(default=None)) -> None:
    """Applied to every route via the app-level `dependencies=` list in
    app/api/app.py, not per-router — a new endpoint added later can't
    accidentally ship without this check.
    """
    settings = get_settings()
    if not settings.api_server_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "API_SERVER_KEY is not configured"
        )
    expected = f"Bearer {settings.api_server_key}"
    # Constant-time comparison — this guards a real secret, not just a
    # display value, so a naive `==` (early-exit on first mismatched
    # byte) would leak timing information about how many leading
    # characters of the token a guess got right.
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")

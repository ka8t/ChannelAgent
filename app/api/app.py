"""Admin API (#22): FastAPI app protected end-to-end by API_SERVER_KEY.

The auth dependency is attached at the app level, not per-router, so
every route — including one added later without remembering to guard
it — requires a valid bearer token.

FastAPI's *automatic* /docs, /redoc, and /openapi.json routes are the
one thing app-level `dependencies=` does NOT cover — they're mounted
by FastAPI's own setup() separately from ordinary path operations, so
they shipped unauthenticated the first time this was verified (#25).
Disabled here (docs_url=None etc.) and re-implemented below as normal
routes, which the app-level dependency does cover.
"""

import logging
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse

from app.admin import service
from app.api.deps import verify_api_key
from app.api.errors import error_responses
from app.api.protect import ProtectMiddleware
from app.api.routes import router
from app.api.scopes import Scope, require, verify_scopes
from app.api.status import router as status_router
from app.api.version import API_VERSION

app = FastAPI(
    title="ChannelAgent Admin API",
    version=API_VERSION,
    dependencies=[Depends(verify_api_key)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.include_router(router)
app.include_router(status_router)
app.add_middleware(ProtectMiddleware)

logger = logging.getLogger("channelagent.api")


def _error(status_code: int):
    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


# One place turns the service layer's errors into HTTP statuses (#41).
app.add_exception_handler(service.NotFoundError, _error(404))
app.add_exception_handler(service.ConflictError, _error(409))
app.add_exception_handler(service.InvalidInputError, _error(422))


@app.get(
    "/openapi.json",
    dependencies=[require(Scope.READ)],
    tags=["system"],
    responses=error_responses(),
)
async def openapi_json() -> dict:
    return get_openapi(title=app.title, version=app.version, routes=app.routes)


@app.get(
    "/docs",
    dependencies=[require(Scope.READ)],
    tags=["system"],
    responses=error_responses(),
)
async def docs() -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Docs")


async def _internal_error(_request: Request, exc: Exception) -> JSONResponse:
    """A short stable message and an id, never the exception text: it can hold a
    path, a query or a value. The details go to the log (redacted) under the id (#108).
    """
    error_id = uuid.uuid4().hex[:12]
    logger.error("Admin API internal error %s", error_id, exc_info=exc)
    return JSONResponse(
        status_code=500, content={"detail": "Internal server error", "error_id": error_id}
    )


app.add_exception_handler(Exception, _internal_error)

# Default deny: the application does not start with a route that declares no scope (#108).
verify_scopes(app)

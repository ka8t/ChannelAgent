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

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

from app.api.deps import verify_api_key
from app.api.routes import router

app = FastAPI(
    title="ChannelAgent Admin API",
    dependencies=[Depends(verify_api_key)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.include_router(router)


@app.get("/openapi.json")
async def openapi_json() -> dict:
    return get_openapi(title=app.title, version=app.version, routes=app.routes)


@app.get("/docs")
async def docs() -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Docs")

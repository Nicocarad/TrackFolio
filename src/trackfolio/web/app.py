"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from plotly.offline import get_plotlyjs

from trackfolio.db import init_db
from trackfolio.web.deps import NotAuthenticated
from trackfolio.web.routes import auth, dashboard, transactions

STATIC_DIR = Path(__file__).parent / "static"


def create_app(migrate: bool = True) -> FastAPI:
    """Create the app; ``migrate=False`` skips the schema upgrade at startup (tests)."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if migrate:
            init_db()
        yield

    app = FastAPI(
        title="TrackFolio", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.get("/static/plotly.min.js", include_in_schema=False)
    def plotly_js() -> Response:
        # Served from the installed plotly package instead of vendoring ~5 MB in the repo.
        return Response(
            get_plotlyjs(),
            media_type="text/javascript",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.exception_handler(NotAuthenticated)
    def not_authenticated(request: Request, _: NotAuthenticated) -> Response:
        if request.headers.get("HX-Request"):
            return Response(status_code=401, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login", status_code=303)

    @app.middleware("http")
    async def reject_cross_site_writes(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Block state-changing requests that browsers mark as coming from another site."""
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            cross_origin = origin and urlparse(origin).netloc != request.headers.get("host")
            if cross_origin or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site request rejected"}, status_code=403)
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(transactions.router)
    return app


app = create_app()

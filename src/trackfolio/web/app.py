"""FastAPI application factory."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from plotly.offline import get_plotlyjs
from sqlalchemy import text
from sqlmodel import Session

from trackfolio.db import init_db
from trackfolio.logging_setup import configure_logging
from trackfolio.web.deps import NotAuthenticated, get_db
from trackfolio.web.routes import auth, dashboard, transactions

STATIC_DIR = Path(__file__).parent / "static"
logger = logging.getLogger(__name__)


def create_app(migrate: bool = True) -> FastAPI:
    """Create the app; ``migrate=False`` skips the schema upgrade at startup (tests)."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if migrate:
            configure_logging()
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

    @app.middleware("http")
    async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        status = 500  # reported if the handler raises
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "ms": round((time.perf_counter() - started) * 1000),
                },
            )

    @app.get("/health", include_in_schema=False)
    def health(session: Session = Depends(get_db)) -> JSONResponse:
        """Liveness and database check for the container health probe."""
        try:
            session.exec(text("SELECT 1"))  # type: ignore[call-overload]
        except Exception:
            logger.exception("Health check failed")
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(transactions.router)
    return app


app = create_app()

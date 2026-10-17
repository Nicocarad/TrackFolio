"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from plotly.offline import get_plotlyjs

from trackfolio.db import init_db
from trackfolio.web.routes import dashboard, transactions

STATIC_DIR = Path(__file__).parent / "static"


def create_app(migrate: bool = True) -> FastAPI:
    """Create the app; ``migrate=False`` skips the schema upgrade at startup (tests)."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if migrate:
            init_db()
        yield

    app = FastAPI(title="TrackFolio", lifespan=lifespan)

    @app.get("/static/plotly.min.js", include_in_schema=False)
    def plotly_js() -> Response:
        # Served from the installed plotly package instead of vendoring ~5 MB in the repo.
        return Response(
            get_plotlyjs(),
            media_type="text/javascript",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(dashboard.router)
    app.include_router(transactions.router)
    return app


app = create_app()

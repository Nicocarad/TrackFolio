"""Shared test doubles and web-client setup."""

import re
from collections.abc import Generator
from datetime import date, timedelta

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from trackfolio.models import Asset
from trackfolio.services.auth_service import AuthService
from trackfolio.web.app import create_app
from trackfolio.web.deps import get_db, get_provider

PASSWORD = "correct horse battery"


class FakeProvider:
    def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
        dates = pd.bdate_range(start=start, end=end - timedelta(days=1))
        return pd.Series([10.0 + i for i in range(len(dates))], index=dates, name=ticker)

    def get_asset(self, ticker: str) -> Asset:
        return Asset(ticker=ticker, name=f"{ticker} Inc", currency="EUR")

    def search_tickers(self, query: str) -> list[Asset]:
        if query.upper() == "NONE":
            return []
        return [self.get_asset(query.upper())]


def memory_engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def open_client(engine: Engine, email: str | None = None) -> Generator[TestClient]:
    """Yield a client for the app on ``engine``; logged in as ``email`` when given.

    The user is created with ``PASSWORD`` if it does not exist yet.
    """

    def override_db() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app = create_app(migrate=False)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as client:
        if email:
            with Session(engine) as session:
                service = AuthService(session)
                try:
                    service.create_user(email, PASSWORD)
                except Exception:  # already exists
                    session.rollback()
            response = client.post(
                "/login", data={"email": email, "password": PASSWORD}, follow_redirects=False
            )
            assert response.status_code == 303
            page = client.get("/transactions")
            token = re.search(r'X-CSRF-Token": "([^"]+)"', page.text)
            assert token, "csrf token missing from the page"
            client.headers["X-CSRF-Token"] = token.group(1)
        yield client

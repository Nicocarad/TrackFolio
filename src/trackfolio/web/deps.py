"""FastAPI dependencies: database session, price provider and portfolio service."""

from collections.abc import Iterator
from functools import cache

from fastapi import Depends, HTTPException
from sqlmodel import Session

from trackfolio.db import get_session
from trackfolio.market_data.provider import PriceProvider
from trackfolio.market_data.yfinance_provider import YFinanceProvider
from trackfolio.models import User
from trackfolio.repositories.users import list_users
from trackfolio.services.portfolio_service import PortfolioService


def get_db() -> Iterator[Session]:
    """Yield one database session per request."""
    with get_session() as session:
        yield session


@cache
def get_provider() -> PriceProvider:
    """Return the shared market-data provider."""
    return YFinanceProvider()


def get_current_user(session: Session = Depends(get_db)) -> User:
    """Return the user of the request.

    Interim, replaced by session authentication in the next change: until then the app
    serves the first user, as the single-user app did.
    """
    users = list_users(session)
    if not users:
        raise HTTPException(status_code=401, detail="No user exists; run `trackfolio create-user`")
    return users[0]


def get_service(
    session: Session = Depends(get_db),
    provider: PriceProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> PortfolioService:
    """Build the portfolio service for the current request."""
    if user.id is None:
        raise HTTPException(status_code=401)
    return PortfolioService(session, provider, user.id)

"""FastAPI dependencies: database session, price provider and portfolio service."""

from collections.abc import Iterator
from functools import cache

from fastapi import Depends
from sqlmodel import Session

from trackfolio.db import get_session
from trackfolio.market_data.provider import PriceProvider
from trackfolio.market_data.yfinance_provider import YFinanceProvider
from trackfolio.services.portfolio_service import PortfolioService


def get_db() -> Iterator[Session]:
    """Yield one database session per request."""
    with get_session() as session:
        yield session


@cache
def get_provider() -> PriceProvider:
    """Return the shared market-data provider."""
    return YFinanceProvider()


def get_service(
    session: Session = Depends(get_db), provider: PriceProvider = Depends(get_provider)
) -> PortfolioService:
    """Build the portfolio service for the current request."""
    return PortfolioService(session, provider)

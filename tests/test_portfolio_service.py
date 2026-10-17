from collections.abc import Generator
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from trackfolio.models import Asset, Transaction, TransactionType
from trackfolio.services.portfolio_service import PortfolioService


class FakeProvider:
    def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
        dates = pd.bdate_range(start=start, end=end - timedelta(days=1))
        return pd.Series([10.0 + index for index in range(len(dates))], index=dates, name=ticker)

    def get_asset(self, ticker: str) -> Asset:
        return Asset(ticker=ticker, name=ticker, currency="EUR")

    def search_tickers(self, query: str) -> list[Asset]:
        return [self.get_asset(query.upper())]


@pytest.fixture
def service() -> Generator[PortfolioService]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield PortfolioService(session, FakeProvider())


def test_service_saves_transaction_and_rejects_removing_required_purchase(
    service: PortfolioService,
) -> None:
    buy = service.save_transaction(
        Transaction(
            date=date.today() - timedelta(days=5),
            ticker="ABC",
            type=TransactionType.BUY,
            quantity=5,
            price=10,
            currency="EUR",
        )
    )
    assert buy.id is not None
    service.save_transaction(
        Transaction(
            date=date.today() - timedelta(days=3),
            ticker="ABC",
            type=TransactionType.SELL,
            quantity=2,
            price=12,
            currency="EUR",
        )
    )

    with pytest.raises(ValueError, match="exceeds holdings"):
        service.delete_transaction(buy.id)
    assert len(service.list_transactions()) == 2


def test_service_refreshes_and_builds_dashboard_from_cached_prices(
    service: PortfolioService,
) -> None:
    service.save_transaction(
        Transaction(
            date=date.today() - timedelta(days=5),
            ticker="ABC",
            type=TransactionType.BUY,
            quantity=2,
            price=10,
            fees=1,
            currency="EUR",
        )
    )

    count, warnings = service.refresh_prices()
    history, holdings, metrics, dashboard_warnings = service.dashboard_data()

    assert count > 0
    assert warnings == []
    assert dashboard_warnings == []
    assert not history.empty
    assert holdings.loc["ABC", "quantity"] == 2
    assert metrics.invested_capital == 21
    assert metrics.total_value > 0

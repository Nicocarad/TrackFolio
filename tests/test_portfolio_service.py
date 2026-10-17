from collections.abc import Generator
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from trackfolio.models import Asset, Transaction, TransactionType
from trackfolio.repositories import assets as assets_repo
from trackfolio.repositories import prices as prices_repo
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


def _buy(ticker: str = "ABC", currency: str = "EUR", days_ago: int = 5) -> Transaction:
    return Transaction(
        date=date.today() - timedelta(days=days_ago),
        ticker=ticker,
        type=TransactionType.BUY,
        quantity=2,
        price=10,
        currency=currency,
    )


def test_failed_save_leaves_no_orphan_asset(service: PortfolioService) -> None:
    with pytest.raises(ValueError, match="does not match"):
        service.save_transaction(_buy(currency="USD"))

    assert assets_repo.get_assets(service.session) == []
    assert service.list_transactions() == []


def test_save_rejects_currency_mismatch_with_stored_asset(service: PortfolioService) -> None:
    service.save_transaction(_buy())
    with pytest.raises(ValueError, match="Multiple currencies|does not match"):
        service.save_transaction(_buy(currency="USD"))
    assert len(service.list_transactions()) == 1


def test_edit_and_delete_only_transaction(service: PortfolioService) -> None:
    saved = service.save_transaction(_buy())
    assert saved.id is not None
    saved.quantity = 3
    service.save_transaction(saved)
    assert service.list_transactions()[0].quantity == 3

    service.delete_transaction(saved.id)
    assert service.list_transactions() == []


def test_refresh_without_transactions(service: PortfolioService) -> None:
    assert service.refresh_prices() == (0, [])


def test_refresh_survives_unexpected_provider_error(service: PortfolioService) -> None:
    service.save_transaction(_buy())

    class Broken(FakeProvider):
        def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
            raise KeyError("boom")

    service.provider = Broken()
    count, warnings = service.refresh_prices()
    assert count == 0
    assert len(warnings) == 1
    assert "cache assente" in warnings[0]


def test_refresh_failure_with_cache_keeps_cache(service: PortfolioService) -> None:
    service.save_transaction(_buy())
    service.refresh_prices()

    class Broken(FakeProvider):
        def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
            raise RuntimeError("down")

    service.provider = Broken()
    _, warnings = service.refresh_prices()
    assert "uso cache" in warnings[0]
    assert not prices_repo.get_prices(service.session, "ABC").empty


def test_refresh_is_incremental_once_cached(service: PortfolioService) -> None:
    service.save_transaction(_buy(days_ago=30))
    service.refresh_prices()
    starts: list[date] = []

    class Spy(FakeProvider):
        def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
            starts.append(start)
            return super().get_history(ticker, start, end)

    service.provider = Spy()
    service.refresh_prices()
    assert starts[0] > date.today() - timedelta(days=15)


def test_dashboard_without_price_cache_warns(service: PortfolioService) -> None:
    service.save_transaction(_buy())
    history, holdings, _, warnings = service.dashboard_data()
    assert history.empty and holdings.empty
    assert warnings


def test_dashboard_non_eur_asset_and_missing_fx(service: PortfolioService) -> None:
    class UsdProvider(FakeProvider):
        def get_asset(self, ticker: str) -> Asset:
            return Asset(ticker=ticker, name=ticker, currency="USD")

        def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
            if ticker.startswith("EUR"):
                raise RuntimeError("no fx")
            return super().get_history(ticker, start, end)

    service.provider = UsdProvider()
    service.save_transaction(_buy("US1", "USD"))
    service.refresh_prices()
    _, _, _, warnings = service.dashboard_data()
    assert any("cambio" in item for item in warnings)

    class WithFx(UsdProvider):
        def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
            return FakeProvider.get_history(self, ticker, start, end).clip(lower=1) / (
                10 if ticker.startswith("EUR") else 1
            )

    service.provider = WithFx()
    service.refresh_prices()
    _, holdings, _, warnings = service.dashboard_data()
    assert warnings == []
    assert holdings.loc["US1", "currency"] == "USD"


def test_dashboard_is_partial_when_one_ticker_has_no_price(service: PortfolioService) -> None:
    service.save_transaction(_buy("AAA"))
    service.save_transaction(_buy("BBB"))
    prices_repo.save_prices(
        service.session,
        "AAA",
        FakeProvider().get_history("AAA", date.today() - timedelta(5), date.today()),
    )
    service.session.commit()

    history, holdings, _, warnings = service.dashboard_data()

    assert not history.empty
    assert list(holdings.index) == ["AAA"]
    assert any("BBB" in item for item in warnings)

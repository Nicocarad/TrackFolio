from collections.abc import Generator
from datetime import date

import pandas as pd
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from trackfolio.models import Asset
from trackfolio.repositories import assets, prices


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)))


def test_save_prices_is_idempotent_and_updates(session: Session) -> None:
    prices.save_prices(session, "abc", _series([1.0, 2.0, 3.0]))
    prices.save_prices(session, "ABC", _series([1.0, 2.0, 3.0]))
    assert len(prices.get_prices(session, "ABC")) == 3

    prices.save_prices(session, "ABC", _series([1.0, 9.0, 3.0]))
    cached = prices.get_prices(session, "abc")
    assert len(cached) == 3
    assert cached.loc[pd.Timestamp("2024-01-02")] == 9.0


def test_save_prices_drops_nan_and_handles_empty(session: Session) -> None:
    prices.save_prices(session, "ABC", _series([1.0, float("nan"), 3.0]))
    assert list(prices.get_prices(session, "ABC")) == [1.0, 3.0]
    prices.save_prices(session, "XYZ", pd.Series([], dtype="float64"))
    assert prices.get_prices(session, "XYZ").empty


def test_latest_price_date(session: Session) -> None:
    assert prices.latest_price_date(session) is None
    prices.save_prices(session, "ABC", _series([1.0, 2.0]))
    assert prices.latest_price_date(session) == date(2024, 1, 2)


def test_save_asset_normalizes_ticker(session: Session) -> None:
    assets.save_asset(session, Asset(ticker="abc", name="A", currency="EUR"))
    assert assets.get_asset(session, "abc") is not None
    assert [a.ticker for a in assets.get_assets(session)] == ["ABC"]


def test_engine_enforces_foreign_keys_and_checks() -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session, SQLModel, create_engine

    from trackfolio.db import configure_engine
    from trackfolio.models import Transaction, TransactionType

    engine = configure_engine(create_engine("sqlite://"))
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Transaction(
                date=date(2024, 1, 2),
                ticker="NOPE",
                type=TransactionType.BUY,
                quantity=1,
                price=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(Asset(ticker="ABC", name="ABC", currency="EUR"))
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    'INSERT INTO "transaction" (date, ticker, type, quantity, price, fees)'
                    " VALUES ('2024-01-02', 'ABC', 'BUY', -1, 1, 0)"
                )
            )

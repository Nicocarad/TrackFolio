"""Daily price cache persistence helpers."""

from datetime import date

import pandas as pd
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, col, select

from trackfolio.models import Price


def get_prices(session: Session, ticker: str) -> pd.Series:
    """Return cached closes indexed by date."""
    ticker = ticker.upper()
    statement = select(Price).where(Price.ticker == ticker).order_by(col(Price.date))
    rows = session.exec(statement).all()
    return pd.Series(
        {pd.Timestamp(row.date): row.close for row in rows},
        dtype="float64",
        name=ticker,
    )


def save_prices(session: Session, ticker: str, prices: pd.Series) -> None:
    """Insert or update daily closes in one bulk upsert."""
    ticker = ticker.upper()
    values = [
        {
            "ticker": ticker,
            "date": timestamp.date() if isinstance(timestamp, pd.Timestamp) else timestamp,
            "close": float(close),
        }
        for timestamp, close in prices.dropna().items()
    ]
    if values:
        statement = insert(Price)
        statement = statement.on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={"close": statement.excluded.close},
        )
        session.exec(statement, params=values)


def latest_price_date(session: Session) -> date | None:
    """Return the most recent cached market-data date."""
    return session.exec(select(func.max(Price.date))).one()

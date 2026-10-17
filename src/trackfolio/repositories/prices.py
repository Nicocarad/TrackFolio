"""Daily price cache persistence helpers."""

from datetime import date

import pandas as pd
from sqlalchemy import func
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.sql.dml import Insert
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


def upsert_statement(dialect_name: str) -> Insert:
    """INSERT ... ON CONFLICT DO UPDATE on (ticker, date) for SQLite or PostgreSQL."""
    insert = postgresql.insert if dialect_name == "postgresql" else sqlite.insert
    statement = insert(Price)
    return statement.on_conflict_do_update(
        index_elements=["ticker", "date"],
        set_={"close": statement.excluded.close},
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
        session.exec(upsert_statement(session.get_bind().dialect.name), params=values)


def latest_price_date(session: Session) -> date | None:
    """Return the most recent cached market-data date."""
    return session.exec(select(func.max(Price.date))).one()

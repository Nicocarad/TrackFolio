"""Daily price cache persistence helpers."""

from datetime import date

import pandas as pd
from sqlmodel import Session, select

from trackfolio.models import Price


def get_prices(session: Session, ticker: str) -> pd.Series:
    """Return cached closes indexed by date."""
    statement = select(Price).where(Price.ticker == ticker).order_by("date")
    rows = session.exec(statement).all()
    return pd.Series(
        {pd.Timestamp(row.date): row.close for row in rows},
        dtype="float64",
        name=ticker,
    )


def save_prices(session: Session, ticker: str, prices: pd.Series) -> None:
    """Insert or update daily closes."""
    for timestamp, close in prices.dropna().items():
        price_date = timestamp.date() if isinstance(timestamp, pd.Timestamp) else timestamp
        row = session.get(Price, (ticker, price_date))
        if row is None:
            row = Price(ticker=ticker, date=price_date, close=float(close))
        else:
            row.close = float(close)
        session.add(row)
    session.commit()


def latest_price_date(session: Session) -> date | None:
    """Return the most recent cached market-data date."""
    statement = select(Price).order_by("date desc").limit(1)
    row = session.exec(statement).first()
    return row.date if row else None

"""Database models for instruments, transactions, and cached market data."""

from datetime import UTC, datetime
from datetime import date as Date
from enum import StrEnum

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class TransactionType(StrEnum):
    """Supported transaction directions."""

    BUY = "BUY"
    SELL = "SELL"


class Asset(SQLModel, table=True):
    """A tradable instrument identified by its provider ticker."""

    ticker: str = Field(primary_key=True, index=True)
    isin: str | None = Field(default=None, index=True)
    exchange: str | None = None
    name: str
    currency: str = Field(min_length=3, max_length=3)
    asset_class: str | None = None


class Transaction(SQLModel, table=True):
    """A manually entered purchase or sale."""

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_transaction_quantity"),
        CheckConstraint("price >= 0", name="ck_transaction_price"),
        CheckConstraint("fees >= 0", name="ck_transaction_fees"),
    )

    id: int | None = Field(default=None, primary_key=True)
    date: Date = Field(index=True)
    ticker: str = Field(foreign_key="asset.ticker", index=True)
    type: TransactionType
    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    fees: float = Field(default=0, ge=0)
    notes: str | None = None


class Price(SQLModel, table=True):
    """Daily closing price cache, keyed by ticker and date."""

    __table_args__ = (CheckConstraint("close >= 0", name="ck_price_close"),)

    ticker: str = Field(primary_key=True)
    date: Date = Field(primary_key=True)
    close: float = Field(ge=0)
    source: str = "yfinance"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

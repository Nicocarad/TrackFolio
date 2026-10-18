"""Database models for instruments, transactions, and cached market data."""

from datetime import UTC, datetime
from datetime import date as Date
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime
from sqlmodel import Field, SQLModel


class TransactionType(StrEnum):
    """Supported transaction directions."""

    BUY = "BUY"
    SELL = "SELL"
    SPLIT = "SPLIT"
    DIVIDEND = "DIVIDEND"


class User(SQLModel, table=True):
    """An account; passwords are stored only as argon2 hashes."""

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    is_admin: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserSession(SQLModel, table=True):
    """A login session; only the SHA-256 of the cookie token is stored."""

    __tablename__ = "user_session"

    token_hash: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    csrf_token: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime


class RateEvent(SQLModel, table=True):
    """One counted event (for example a failed login) for the database-backed rate limiter."""

    __tablename__ = "rate_event"

    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    key: str = Field(index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )


class InstrumentCache(SQLModel, table=True):
    """Persistent instrument search results; ``payload`` is a JSON list of Asset fields."""

    __tablename__ = "instrument_cache"

    query_key: str = Field(primary_key=True)
    payload: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )


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
    user_id: int = Field(foreign_key="user.id", index=True)
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

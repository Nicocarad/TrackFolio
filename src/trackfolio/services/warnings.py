"""Structured warnings shared by the services; wording and language belong to the caller."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trackfolio.errors import DomainError


class WarningCode(StrEnum):
    """Kinds of data problems the service reports without hiding the rest of the result."""

    NO_PRICE = "no_price"  # subject: ticker
    NO_FX = "no_fx"  # subject: currency
    EXCLUDED = "excluded"  # subject: comma-separated tickers left out of the dashboard
    REFRESH_FAILED = "refresh_failed"  # subject: ticker, detail: error, cached_until if any
    DATA_ERROR = "data_error"  # detail: technical message


@dataclass(frozen=True)
class DataWarning:
    """A structured warning; presentation and language are up to the caller."""

    code: WarningCode
    subject: str = ""
    detail: str = ""
    cached_until: date | None = None
    error: DomainError | None = None  # set for DATA_ERROR when the cause is a domain error

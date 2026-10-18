"""Domain errors with a stable code so the presentation layer can translate them."""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Every user-facing validation or data error."""

    INVALID_VALUES = "invalid_values"
    FUTURE_DATE = "future_date"
    TICKER_REQUIRED = "ticker_required"
    INVALID_TYPE = "invalid_type"
    QUANTITY_NOT_POSITIVE = "quantity_not_positive"
    NEGATIVE_AMOUNT = "negative_amount"
    SPLIT_HAS_PRICE = "split_has_price"
    OVERSELL = "oversell"
    SELL_EXCEEDS = "sell_exceeds"
    DIVIDEND_EXCEEDS = "dividend_exceeds"
    TRANSACTION_NOT_FOUND = "transaction_not_found"
    MISSING_COLUMNS = "missing_columns"
    UNKNOWN_TYPE = "unknown_type"
    NO_PRICES = "no_prices"
    MISSING_PRICE_SERIES = "missing_price_series"
    MISSING_CURRENCY = "missing_currency"
    MISSING_FX = "missing_fx"
    UNPRICED_HOLDINGS = "unpriced_holdings"
    INVALID_ISIN = "invalid_isin"
    EMPTY_QUERY = "empty_query"
    UNKNOWN_TICKER = "unknown_ticker"
    NO_HISTORY = "no_history"
    EMAIL_INVALID = "email_invalid"
    EMAIL_TAKEN = "email_taken"
    PASSWORD_TOO_SHORT = "password_too_short"
    USER_NOT_FOUND = "user_not_found"
    RATE_LIMITED = "rate_limited"


MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_VALUES: "Transaction contains invalid or missing values",
    ErrorCode.FUTURE_DATE: "Transaction date cannot be in the future",
    ErrorCode.TICKER_REQUIRED: "Ticker is required",
    ErrorCode.INVALID_TYPE: "Transaction type must be one of {allowed}",
    ErrorCode.QUANTITY_NOT_POSITIVE: "Quantity must be greater than zero",
    ErrorCode.NEGATIVE_AMOUNT: "Price and fees cannot be negative",
    ErrorCode.SPLIT_HAS_PRICE: "A split has no price or fees; quantity is the split ratio",
    ErrorCode.OVERSELL: (
        "Cannot sell {quantity:g} of {ticker} on {date}; holdings would be negative ({holdings:g})"
    ),
    ErrorCode.SELL_EXCEEDS: "Sell transaction exceeds holdings for {ticker} on {date}",
    ErrorCode.DIVIDEND_EXCEEDS: (
        "Dividend on {quantity:g} of {ticker} on {date} exceeds holdings ({holdings:g})"
    ),
    ErrorCode.TRANSACTION_NOT_FOUND: "Transaction {transaction_id} does not exist",
    ErrorCode.MISSING_COLUMNS: "Missing transaction columns: {columns}",
    ErrorCode.UNKNOWN_TYPE: "Unknown transaction type: {types}",
    ErrorCode.NO_PRICES: "At least one price observation is required",
    ErrorCode.MISSING_PRICE_SERIES: "Missing price series for: {tickers}",
    ErrorCode.MISSING_CURRENCY: "Missing currency for: {tickers}",
    ErrorCode.MISSING_FX: "Missing FX rates for: {currencies}",
    ErrorCode.UNPRICED_HOLDINGS: "Holdings without a price before first quote for: {tickers}",
    ErrorCode.INVALID_ISIN: "ISIN is invalid (format or check digit)",
    ErrorCode.EMPTY_QUERY: "Enter an ISIN or ticker",
    ErrorCode.UNKNOWN_TICKER: "Yahoo Finance does not recognize ticker {ticker}",
    ErrorCode.NO_HISTORY: "No price history returned for {ticker}",
    ErrorCode.EMAIL_INVALID: "Invalid email address",
    ErrorCode.EMAIL_TAKEN: "A user with email {email} already exists",
    ErrorCode.PASSWORD_TOO_SHORT: "Password must be at least {minimum} characters",
    ErrorCode.USER_NOT_FOUND: "No user with email {email}",
    ErrorCode.RATE_LIMITED: "Too many attempts; retry in {seconds} seconds",
}


class DomainError(ValueError):
    """A ``ValueError`` carrying a code and parameters; its text is the English message."""

    def __init__(self, code: ErrorCode, **params: Any) -> None:
        self.code = code
        self.params = params
        super().__init__(MESSAGES[code].format(**params))

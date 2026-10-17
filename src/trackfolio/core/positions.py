"""Position and cost-basis calculations without I/O."""

import math
from datetime import date
from decimal import Decimal
from numbers import Real

import pandas as pd

from trackfolio.errors import DomainError, ErrorCode
from trackfolio.models import TransactionType

_EPSILON = 1e-9


# Within a day: splits first, then purchases, then dividends, then sales, so the entry order
# of one day's transactions cannot make a valid history look oversold.
_ORDER = {
    TransactionType.SPLIT.value: 0,
    TransactionType.BUY.value: 1,
    TransactionType.DIVIDEND.value: 2,
    TransactionType.SELL.value: 3,
}


def order_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Normalize ticker/type/date and sort transactions chronologically."""
    required = {"date", "ticker", "type", "quantity", "price", "fees"}
    missing = required.difference(transactions.columns)
    if missing:
        raise DomainError(ErrorCode.MISSING_COLUMNS, columns=", ".join(sorted(missing)))
    result = transactions.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.date
    result["ticker"] = result["ticker"].str.upper()
    result["type"] = result["type"].astype(str).str.upper()
    unknown = set(result["type"]).difference(_ORDER)
    if unknown:
        raise DomainError(ErrorCode.UNKNOWN_TYPE, types=", ".join(sorted(unknown)))
    result["_rank"] = result["type"].map(_ORDER)
    keys = ["date", "_rank", "id"] if "id" in result.columns else ["date", "_rank"]
    return result.sort_values(keys, kind="stable").drop(columns="_rank")


def validate_transaction(
    transaction: dict[str, object],
    existing: pd.DataFrame,
    transaction_id: int | None = None,
    today: date | None = None,
) -> None:
    """Validate transaction fields and ensure a sale does not exceed holdings."""
    try:
        tx_date = pd.Timestamp(transaction["date"]).date()
        ticker = str(transaction["ticker"]).upper()
        tx_type = str(transaction["type"]).upper()
        quantity = _number(transaction["quantity"], "quantity")
        price = _number(transaction["price"], "price")
        fees = _number(transaction.get("fees", 0), "fees")
    except (KeyError, TypeError, ValueError) as error:
        raise DomainError(ErrorCode.INVALID_VALUES) from error
    if tx_date > (today or date.today()):
        raise DomainError(ErrorCode.FUTURE_DATE)
    if not ticker:
        raise DomainError(ErrorCode.TICKER_REQUIRED)
    if tx_type not in _ORDER:
        raise DomainError(ErrorCode.INVALID_TYPE, allowed=", ".join(_ORDER))
    if quantity <= 0:
        raise DomainError(ErrorCode.QUANTITY_NOT_POSITIVE)
    if price < 0 or fees < 0:
        raise DomainError(ErrorCode.NEGATIVE_AMOUNT)
    if tx_type == TransactionType.SPLIT.value and (price or fees):
        raise DomainError(ErrorCode.SPLIT_HAS_PRICE)

    history = existing.copy()
    if not history.empty and transaction_id is not None and "id" in history:
        history = history[history["id"] != transaction_id]
    proposed = {**transaction, "date": tx_date, "ticker": ticker, "type": tx_type}
    proposed.update(quantity=quantity, price=price, fees=fees)
    history = pd.concat([history, pd.DataFrame([proposed])], ignore_index=True)
    history = order_transactions(history)
    history = history[history["ticker"] == ticker]
    holdings = 0.0
    for row in history.itertuples(index=False):
        if row.type == TransactionType.SPLIT.value:
            holdings *= row.quantity
        elif row.type == TransactionType.DIVIDEND.value:
            if row.quantity > holdings + _EPSILON:
                raise DomainError(
                    ErrorCode.DIVIDEND_EXCEEDS,
                    quantity=row.quantity,
                    ticker=ticker,
                    date=row.date,
                    holdings=holdings,
                )
        else:
            holdings += row.quantity if row.type == TransactionType.BUY.value else -row.quantity
            if holdings < -_EPSILON:
                raise DomainError(
                    ErrorCode.OVERSELL,
                    quantity=row.quantity,
                    ticker=ticker,
                    date=row.date,
                    holdings=holdings,
                )


def _number(value: object, name: str) -> float:
    """Convert numeric transaction input without accepting arbitrary objects."""
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def calculate_positions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Calculate quantity, average cost, realized P&L and net dividends per ticker.

    A split multiplies the quantity and divides the average cost by its ratio; a dividend
    adds ``quantity * price - fees`` to ``dividends`` and leaves the position unchanged.
    """
    columns = ["quantity", "average_cost", "realized_pnl", "dividends"]
    if transactions.empty:
        return pd.DataFrame(columns=columns, dtype="float64").rename_axis("ticker")

    ordered = order_transactions(transactions)
    positions: dict[str, dict[str, float]] = {}
    for row in ordered.itertuples(index=False):
        position = positions.setdefault(
            row.ticker,
            {"quantity": 0.0, "average_cost": 0.0, "realized_pnl": 0.0, "dividends": 0.0},
        )
        if row.type == TransactionType.BUY.value:
            new_quantity = position["quantity"] + row.quantity
            total_cost = position["quantity"] * position["average_cost"]
            total_cost += row.quantity * row.price + row.fees
            position["average_cost"] = total_cost / new_quantity
            position["quantity"] = new_quantity
        elif row.type == TransactionType.SELL.value:
            if row.quantity > position["quantity"] + _EPSILON:
                raise DomainError(ErrorCode.SELL_EXCEEDS, ticker=row.ticker, date=row.date)
            position["realized_pnl"] += (
                row.quantity * (row.price - position["average_cost"]) - row.fees
            )
            position["quantity"] = max(0.0, position["quantity"] - row.quantity)
            if position["quantity"] <= _EPSILON:
                position["quantity"] = 0.0
                position["average_cost"] = 0.0
        elif row.type == TransactionType.SPLIT.value:
            position["quantity"] *= row.quantity
            position["average_cost"] /= row.quantity
        else:
            if row.quantity > position["quantity"] + _EPSILON:
                raise DomainError(
                    ErrorCode.DIVIDEND_EXCEEDS,
                    quantity=row.quantity,
                    ticker=row.ticker,
                    date=row.date,
                    holdings=position["quantity"],
                )
            position["dividends"] += row.quantity * row.price - row.fees
    return (
        pd.DataFrame.from_dict(positions, orient="index")
        .reindex(columns=columns)
        .rename_axis("ticker")
    )

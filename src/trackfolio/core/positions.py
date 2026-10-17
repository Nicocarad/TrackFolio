"""Position and cost-basis calculations without I/O."""

import math
from datetime import date
from decimal import Decimal
from numbers import Real

import pandas as pd

from trackfolio.models import TransactionType

_EPSILON = 1e-9


def _ordered(transactions: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "ticker", "type", "quantity", "price", "fees"}
    missing = required.difference(transactions.columns)
    if missing:
        raise ValueError(f"Missing transaction columns: {', '.join(sorted(missing))}")
    result = transactions.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.date
    result["ticker"] = result["ticker"].str.upper()
    result["type"] = result["type"].astype(str).str.upper()
    # BUY before SELL within a day, so entry order cannot make a valid day look oversold.
    result["_sell"] = result["type"] == TransactionType.SELL.value
    keys = ["date", "_sell", "id"] if "id" in result.columns else ["date", "_sell"]
    return result.sort_values(keys, kind="stable").drop(columns="_sell")


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
        raise ValueError("Transaction contains invalid or missing values") from error
    if tx_date > (today or date.today()):
        raise ValueError("Transaction date cannot be in the future")
    if not ticker:
        raise ValueError("Ticker is required")
    if tx_type not in {TransactionType.BUY.value, TransactionType.SELL.value}:
        raise ValueError("Transaction type must be BUY or SELL")
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")
    if price < 0 or fees < 0:
        raise ValueError("Price and fees cannot be negative")

    history = existing.copy()
    if not history.empty and transaction_id is not None and "id" in history:
        history = history[history["id"] != transaction_id]
    proposed = {**transaction, "date": tx_date, "ticker": ticker, "type": tx_type}
    proposed.update(quantity=quantity, price=price, fees=fees)
    history = pd.concat([history, pd.DataFrame([proposed])], ignore_index=True)
    history = _ordered(history)
    history = history[history["ticker"] == ticker]
    _check_currencies(history)
    holdings = 0.0
    for row in history.itertuples(index=False):
        holdings += row.quantity if row.type == TransactionType.BUY.value else -row.quantity
        if holdings < -_EPSILON:
            raise ValueError(
                f"Cannot sell {row.quantity:g} of {ticker} on {row.date}; "
                f"holdings would be negative ({holdings:g})"
            )


def _check_currencies(transactions: pd.DataFrame) -> None:
    """Reject a ticker traded in more than one currency (cost basis would mix them)."""
    if "currency" not in transactions.columns:
        return
    currencies = transactions.dropna(subset=["currency"]).groupby("ticker")["currency"]
    for ticker, values in currencies:
        if values.astype(str).str.upper().nunique() > 1:
            raise ValueError(f"Multiple currencies for {ticker} are not supported")


def _number(value: object, name: str) -> float:
    """Convert numeric transaction input without accepting arbitrary objects."""
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def calculate_positions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Calculate current quantity, weighted average cost, and realized P&L per ticker."""
    columns = ["quantity", "average_cost", "realized_pnl"]
    if transactions.empty:
        return pd.DataFrame(columns=columns, dtype="float64").rename_axis("ticker")

    ordered = _ordered(transactions)
    _check_currencies(ordered)
    positions: dict[str, dict[str, float]] = {}
    for row in ordered.itertuples(index=False):
        position = positions.setdefault(
            row.ticker, {"quantity": 0.0, "average_cost": 0.0, "realized_pnl": 0.0}
        )
        if row.type == TransactionType.BUY.value:
            new_quantity = position["quantity"] + row.quantity
            total_cost = position["quantity"] * position["average_cost"]
            total_cost += row.quantity * row.price + row.fees
            position["average_cost"] = total_cost / new_quantity
            position["quantity"] = new_quantity
        elif row.type == TransactionType.SELL.value:
            if row.quantity > position["quantity"] + _EPSILON:
                raise ValueError(
                    f"Sell transaction exceeds holdings for {row.ticker} on {row.date}"
                )
            position["realized_pnl"] += (
                row.quantity * (row.price - position["average_cost"]) - row.fees
            )
            position["quantity"] = max(0.0, position["quantity"] - row.quantity)
            if position["quantity"] <= _EPSILON:
                position["quantity"] = 0.0
                position["average_cost"] = 0.0
        else:
            raise ValueError(f"Unsupported transaction type: {row.type}")
    return (
        pd.DataFrame.from_dict(positions, orient="index")
        .reindex(columns=columns)
        .rename_axis("ticker")
    )

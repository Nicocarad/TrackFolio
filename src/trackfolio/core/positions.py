"""Position and cost-basis calculations without I/O."""

from datetime import date

import pandas as pd

from trackfolio.models import TransactionType


def _ordered(transactions: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "ticker", "type", "quantity", "price", "fees"}
    missing = required.difference(transactions.columns)
    if missing:
        raise ValueError(f"Missing transaction columns: {', '.join(sorted(missing))}")
    result = transactions.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.date
    result["ticker"] = result["ticker"].str.upper()
    result["type"] = result["type"].astype(str).str.upper()
    if "id" in result.columns:
        result = result.sort_values(["date", "id"], kind="stable")
    else:
        result = result.sort_values(["date"], kind="stable")
    return result


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
    if tx_type != TransactionType.SELL.value:
        return

    holdings = 0.0
    if not existing.empty:
        history = _ordered(existing)
        if transaction_id is not None and "id" in history:
            history = history[history["id"] != transaction_id]
        history = history[(history["ticker"] == ticker) & (history["date"] <= tx_date)]
        for row in history.itertuples(index=False):
            holdings += row.quantity if row.type == TransactionType.BUY.value else -row.quantity
    if quantity > holdings + 1e-9:
        raise ValueError(
            f"Cannot sell {quantity:g}; only {max(holdings, 0):g} available on {tx_date}"
        )


def _number(value: object, name: str) -> float:
    """Convert numeric transaction input without accepting arbitrary objects."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def calculate_positions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Calculate current quantity, weighted average cost, and realized P&L per ticker."""
    columns = ["quantity", "average_cost", "realized_pnl"]
    if transactions.empty:
        return pd.DataFrame(columns=columns, dtype="float64").rename_axis("ticker")

    positions: dict[str, dict[str, float]] = {}
    for row in _ordered(transactions).itertuples(index=False):
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
            if row.quantity > position["quantity"] + 1e-9:
                raise ValueError(
                    f"Sell transaction exceeds holdings for {row.ticker} on {row.date}"
                )
            position["realized_pnl"] += (
                row.quantity * (row.price - position["average_cost"]) - row.fees
            )
            position["quantity"] = max(0.0, position["quantity"] - row.quantity)
            if position["quantity"] == 0:
                position["average_cost"] = 0.0
        else:
            raise ValueError(f"Unsupported transaction type: {row.type}")
    return (
        pd.DataFrame.from_dict(positions, orient="index")
        .reindex(columns=columns)
        .rename_axis("ticker")
    )

from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from trackfolio.core.positions import calculate_positions, validate_transaction


def test_weighted_cost_and_realized_profit() -> None:
    transactions = pd.DataFrame(
        [
            {
                "date": "2025-01-01",
                "ticker": "ABC",
                "type": "BUY",
                "quantity": 2,
                "price": 10,
                "fees": 2,
            },
            {
                "date": "2025-01-02",
                "ticker": "ABC",
                "type": "BUY",
                "quantity": 2,
                "price": 20,
                "fees": 0,
            },
            {
                "date": "2025-01-03",
                "ticker": "ABC",
                "type": "SELL",
                "quantity": 1,
                "price": 30,
                "fees": 1,
            },
        ]
    )
    position = calculate_positions(transactions).loc["ABC"]
    assert position["quantity"] == 3
    assert position["average_cost"] == 15.5
    assert position["realized_pnl"] == 13.5


def test_sell_more_than_owned_is_rejected() -> None:
    transactions = pd.DataFrame(
        [
            {
                "date": "2025-01-01",
                "ticker": "ABC",
                "type": "BUY",
                "quantity": 2,
                "price": 10,
                "fees": 0,
            },
            {
                "date": "2025-01-02",
                "ticker": "ABC",
                "type": "SELL",
                "quantity": 3,
                "price": 10,
                "fees": 0,
            },
        ]
    )
    with pytest.raises(ValueError, match="exceeds holdings"):
        calculate_positions(transactions)


def test_validate_sale_uses_holdings_as_of_sale_date() -> None:
    existing = pd.DataFrame(
        [
            {
                "date": "2025-01-01",
                "ticker": "ABC",
                "type": "BUY",
                "quantity": 3,
                "price": 1,
                "fees": 0,
            }
        ]
    )
    proposed = {
        "date": date(2025, 1, 2),
        "ticker": "ABC",
        "type": "SELL",
        "quantity": 3,
        "price": 1,
        "fees": 0,
    }
    validate_transaction(proposed, existing, today=date(2025, 1, 3))


def test_future_transactions_are_rejected() -> None:
    proposed = {
        "date": date.today() + timedelta(days=1),
        "ticker": "ABC",
        "type": "BUY",
        "quantity": 1,
        "price": 1,
        "fees": 0,
    }
    with pytest.raises(ValueError, match="future"):
        validate_transaction(proposed, pd.DataFrame())


def _tx(day: str, kind: str, qty: float, ticker: str = "ABC", **extra: object) -> dict[str, object]:
    return {
        "date": day,
        "ticker": ticker,
        "type": kind,
        "quantity": qty,
        "price": 10,
        "fees": 0,
        **extra,
    }


def test_same_day_sell_entered_before_buy() -> None:
    frame = pd.DataFrame([_tx("2025-01-01", "SELL", 1, id=1), _tx("2025-01-01", "BUY", 1, id=2)])
    assert calculate_positions(frame).loc["ABC", "quantity"] == 0
    validate_transaction(_tx("2025-01-01", "SELL", 1), pd.DataFrame([_tx("2025-01-01", "BUY", 1)]))


def test_back_dated_sell_cannot_starve_later_sell() -> None:
    existing = pd.DataFrame([_tx("2025-01-01", "BUY", 3), _tx("2025-01-05", "SELL", 3)])
    with pytest.raises(ValueError, match="negative"):
        validate_transaction(_tx("2025-01-02", "SELL", 1), existing, today=date(2025, 2, 1))


def test_edit_excludes_own_id_and_replays_history() -> None:
    existing = pd.DataFrame([_tx("2025-01-01", "BUY", 3, id=1), _tx("2025-01-02", "SELL", 3, id=2)])
    validate_transaction(_tx("2025-01-02", "SELL", 2), existing, 2, today=date(2025, 2, 1))
    with pytest.raises(ValueError, match="negative"):
        validate_transaction(_tx("2025-01-01", "BUY", 1), existing, 1, today=date(2025, 2, 1))


def test_full_exit_then_rebuy_resets_cost() -> None:
    frame = pd.DataFrame(
        [_tx("2025-01-01", "BUY", 1), _tx("2025-01-02", "SELL", 1), _tx("2025-01-03", "BUY", 2)]
    )
    frame.loc[2, "price"] = 20
    position = calculate_positions(frame).loc["ABC"]
    assert position["quantity"] == 2
    assert position["average_cost"] == 20


def test_float_residual_closes_position() -> None:
    frame = pd.DataFrame([_tx("2025-01-01", "BUY", 0.3), _tx("2025-01-02", "SELL", 0.3 - 1e-12)])
    position = calculate_positions(frame).loc["ABC"]
    assert position["quantity"] == 0
    assert position["average_cost"] == 0


def test_multiple_tickers_are_independent() -> None:
    frame = pd.DataFrame([_tx("2025-01-01", "BUY", 1, "AAA"), _tx("2025-01-02", "BUY", 2, "BBB")])
    positions = calculate_positions(frame)
    assert positions["quantity"].to_dict() == {"AAA": 1, "BBB": 2}
    with pytest.raises(ValueError, match="negative"):
        validate_transaction(
            _tx("2025-01-03", "SELL", 2, "BBB"),
            pd.DataFrame([_tx("2025-01-01", "BUY", 1, "BBB")]),
            today=date(2025, 2, 1),
        )


@pytest.mark.parametrize("value", [np.int64(2), np.float64(2.5), Decimal("2.5")])
def test_numeric_types_accepted(value: object) -> None:
    validate_transaction({**_tx("2025-01-01", "BUY", 1), "quantity": value}, pd.DataFrame())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1"])
def test_non_finite_or_non_numeric_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="invalid"):
        validate_transaction({**_tx("2025-01-01", "BUY", 1), "quantity": value}, pd.DataFrame())

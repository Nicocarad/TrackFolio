from datetime import date, timedelta

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

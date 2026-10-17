import pandas as pd

from trackfolio.core.timeseries import build_portfolio_timeseries


def test_portfolio_value_and_invested_capital() -> None:
    transactions = pd.DataFrame(
        [
            {
                "date": "2025-01-06",
                "ticker": "ABC",
                "type": "BUY",
                "quantity": 2,
                "price": 10,
                "fees": 2,
                "currency": "EUR",
            }
        ]
    )
    dates = pd.to_datetime(["2025-01-06", "2025-01-07"])
    prices = pd.DataFrame({"ABC": [10, 12]}, index=dates)
    history = build_portfolio_timeseries(transactions, prices)
    assert history.iloc[-1]["value"] == 24
    assert history.iloc[-1]["invested_capital"] == 22


def test_converts_foreign_prices_and_transaction_costs_to_eur() -> None:
    transactions = pd.DataFrame(
        [
            {
                "date": "2025-01-06",
                "ticker": "USD",
                "type": "BUY",
                "quantity": 2,
                "price": 100,
                "fees": 2,
                "currency": "USD",
            }
        ]
    )
    dates = pd.to_datetime(["2025-01-06", "2025-01-07"])
    prices = pd.DataFrame({"USD": [100, 110]}, index=dates)
    fx = pd.DataFrame({"EUR": [1, 1], "USD": [0.9, 0.9]}, index=dates)
    history = build_portfolio_timeseries(transactions, prices, fx)
    assert history.iloc[-1]["value"] == 198
    assert history.iloc[-1]["invested_capital"] == 181.8


def test_weekend_transaction_is_counted_on_next_business_day() -> None:
    transactions = pd.DataFrame(
        [
            {
                "date": "2025-01-04",
                "ticker": "ABC",
                "type": "BUY",
                "quantity": 1,
                "price": 10,
                "fees": 0,
                "currency": "EUR",
            }
        ]
    )
    prices = pd.DataFrame({"ABC": [10]}, index=pd.to_datetime(["2025-01-03"]))
    history = build_portfolio_timeseries(transactions, prices)
    assert history.iloc[-1]["value"] == 10
    assert history.iloc[-1]["invested_capital"] == 10

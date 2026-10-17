import pandas as pd
import pytest

from trackfolio.core.holdings import build_holdings


def test_holdings_values_pnl_percent_and_eur_amounts() -> None:
    positions = pd.DataFrame(
        {
            "quantity": [10.0, 2.0],
            "average_cost": [10.0, 50.0],
            "realized_pnl": [5.0, 0.0],
            "dividends": [4.0, 10.0],
        },
        index=pd.Index(["ABC", "USD1"], name="ticker"),
    )
    days = pd.to_datetime(["2025-01-06", "2025-01-07"])
    prices = pd.DataFrame({"ABC": [11.0, 12.0], "USD1": [55.0, 60.0]}, index=days)
    fx = pd.DataFrame({"EUR": [1.0, 1.0], "USD": [0.8, 0.9]}, index=days)
    info = {"ABC": ("ABC Inc", "EUR"), "USD1": ("US One", "USD")}

    holdings = build_holdings(positions, prices, fx, info)

    abc, usd = holdings.loc["ABC"], holdings.loc["USD1"]
    assert abc["profit_loss"] == pytest.approx(20)  # 10 * (12 - 10)
    assert abc["profit_loss_pct"] == pytest.approx(20)  # 12 / 10 - 1
    assert abc["profit_loss_eur"] == pytest.approx(20)
    assert usd["value_eur"] == pytest.approx(2 * 60 * 0.9)
    assert usd["profit_loss_eur"] == pytest.approx(2 * 10 * 0.9)
    assert usd["dividends_eur"] == pytest.approx(9)
    assert abc["realized_pnl_eur"] == pytest.approx(5)


def test_zero_average_cost_has_no_percentage() -> None:
    positions = pd.DataFrame(
        {"quantity": [0.0], "average_cost": [0.0], "realized_pnl": [3.0], "dividends": [0.0]},
        index=pd.Index(["ABC"], name="ticker"),
    )
    days = pd.to_datetime(["2025-01-06"])
    holdings = build_holdings(
        positions,
        pd.DataFrame({"ABC": [10.0]}, index=days),
        pd.DataFrame({"EUR": [1.0]}, index=days),
        {"ABC": ("ABC", "EUR")},
    )
    assert pd.isna(holdings.loc["ABC", "profit_loss_pct"])

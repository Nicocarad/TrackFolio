import pandas as pd
import pytest

from trackfolio.core.returns import daily_twr_returns, period_returns_pct, twr_pct, xirr_pct


def _history(values: list[float], invested: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame({"value": values, "invested_capital": invested}, index=index)


def test_twr_ignores_cash_flow_timing() -> None:
    # +10% on 100, then +100 invested and +9.0909% on 110 -> 1.1 * 1.090909 = 1.2
    history = _history([100, 110, 220], [100, 100, 200])
    assert twr_pct(history) == pytest.approx(20.0)


def test_twr_with_profitable_exit_is_still_defined() -> None:
    # Invest 100, grow to 150, withdraw everything: invested capital goes to -50.
    history = _history([100, 150, 0], [100, 100, -50])
    assert daily_twr_returns(history).tolist() == pytest.approx([0.5, 0.0])
    assert twr_pct(history) == pytest.approx(50.0)


def test_twr_empty_or_single_day_is_none() -> None:
    assert twr_pct(_history([100], [100])) is None


def test_xirr_matches_hand_computed_rate() -> None:
    # 100 invested, 121 two years (730 days) later -> 10% per year.
    index = pd.DatetimeIndex(["2022-01-01", "2023-01-01", "2024-01-01"])
    history = pd.DataFrame(
        {"value": [100, 110, 121], "invested_capital": [100, 100, 100]}, index=index
    )
    assert xirr_pct(history) == pytest.approx(10.0, abs=1e-6)


def test_xirr_handles_total_loss_and_undefined() -> None:
    assert xirr_pct(pd.DataFrame(columns=["value", "invested_capital"])) is None
    flat = _history([0, 0], [0, 0])
    assert xirr_pct(flat) is None


def test_period_returns_need_enough_history() -> None:
    history = _history([100, 110], [100, 100], start="2024-06-01")
    periods = period_returns_pct(history)
    assert periods["1Y"] is None
    assert periods["3Y"] is None
    assert periods["YTD"] is None  # history starts after 31 Dec of the previous year

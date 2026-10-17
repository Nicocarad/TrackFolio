import pandas as pd
import pytest

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
    assert history.iloc[-1]["value"] == pytest.approx(24)
    assert history.iloc[-1]["invested_capital"] == pytest.approx(22)


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
    assert history.iloc[-1]["value"] == pytest.approx(198)
    assert history.iloc[-1]["invested_capital"] == pytest.approx(181.8)


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
    assert history.iloc[-1]["value"] == pytest.approx(10)
    assert history.iloc[-1]["invested_capital"] == pytest.approx(10)


def _tx(
    date: str,
    ticker: str,
    kind: str,
    qty: float,
    price: float,
    fees: float = 0,
    currency: str = "EUR",
) -> dict[str, object]:
    return {
        "date": date,
        "ticker": ticker,
        "type": kind,
        "quantity": qty,
        "price": price,
        "fees": fees,
        "currency": currency,
    }


def _days(*days: str) -> pd.DatetimeIndex:
    return pd.to_datetime(list(days))


def test_sell_with_fees_reduces_invested_capital_by_net_proceeds() -> None:
    tx = pd.DataFrame(
        [_tx("2025-01-06", "ABC", "BUY", 2, 10), _tx("2025-01-07", "ABC", "SELL", 1, 12, 1)]
    )
    prices = pd.DataFrame({"ABC": [10, 12]}, index=_days("2025-01-06", "2025-01-07"))
    last = build_portfolio_timeseries(tx, prices).iloc[-1]
    assert last["value"] == pytest.approx(12)
    assert last["invested_capital"] == pytest.approx(20 - 11)


def test_asset_currency_map_overrides_transaction_currency() -> None:
    # USD-quoted asset bought in EUR: price converted with USD, cash flow with EUR.
    tx = pd.DataFrame([_tx("2025-01-06", "ETF", "BUY", 1, 90, currency="EUR")])
    idx = _days("2025-01-06", "2025-01-07")
    prices = pd.DataFrame({"ETF": [100, 100]}, index=idx)
    fx = pd.DataFrame({"EUR": [1, 1], "USD": [0.9, 0.8]}, index=idx)
    last = build_portfolio_timeseries(tx, prices, fx, {"ETF": "USD"}).iloc[-1]
    assert last["value"] == pytest.approx(80)
    assert last["invested_capital"] == pytest.approx(90)


def test_mixed_currencies() -> None:
    tx = pd.DataFrame(
        [
            _tx("2025-01-06", "AAA", "BUY", 1, 10),
            _tx("2025-01-06", "BBB", "BUY", 1, 100, currency="USD"),
        ]
    )
    idx = _days("2025-01-06")
    prices = pd.DataFrame({"AAA": [10], "BBB": [100]}, index=idx)
    fx = pd.DataFrame({"EUR": [1], "USD": [0.5]}, index=idx)
    last = build_portfolio_timeseries(tx, prices, fx).iloc[-1]
    assert last["value"] == pytest.approx(60)
    assert last["invested_capital"] == pytest.approx(60)


def test_missing_fx_rate_raises() -> None:
    tx = pd.DataFrame([_tx("2025-01-06", "BBB", "BUY", 1, 100, currency="USD")])
    prices = pd.DataFrame({"BBB": [100]}, index=_days("2025-01-06"))
    with pytest.raises(ValueError, match="Missing FX rates"):
        build_portfolio_timeseries(tx, prices)


def test_missing_price_series_raises() -> None:
    tx = pd.DataFrame([_tx("2025-01-06", "ABC", "BUY", 1, 10)])
    prices = pd.DataFrame({"OTHER": [1]}, index=_days("2025-01-06"))
    with pytest.raises(ValueError, match="Missing price series"):
        build_portfolio_timeseries(tx, prices)


def test_price_gap_is_forward_filled() -> None:
    tx = pd.DataFrame([_tx("2025-01-06", "ABC", "BUY", 1, 10)])
    prices = pd.DataFrame({"ABC": [10, 14]}, index=_days("2025-01-06", "2025-01-09"))
    history = build_portfolio_timeseries(tx, prices)
    assert history["value"].tolist() == pytest.approx([10, 10, 10, 14])


def test_two_transactions_on_one_day() -> None:
    tx = pd.DataFrame(
        [_tx("2025-01-06", "ABC", "BUY", 2, 10), _tx("2025-01-06", "ABC", "SELL", 1, 10)]
    )
    prices = pd.DataFrame({"ABC": [10]}, index=_days("2025-01-06"))
    last = build_portfolio_timeseries(tx, prices).iloc[-1]
    assert last["value"] == pytest.approx(10)
    assert last["invested_capital"] == pytest.approx(10)


def test_empty_transactions_return_empty_frame() -> None:
    history = build_portfolio_timeseries(pd.DataFrame(), pd.DataFrame())
    assert history.empty
    assert list(history.columns) == ["value", "invested_capital"]


def test_untraded_price_column_is_ignored() -> None:
    tx = pd.DataFrame([_tx("2025-01-06", "ABC", "BUY", 1, 10)])
    prices = pd.DataFrame({"ABC": [10], "EXTRA": [5]}, index=_days("2025-01-06"))
    assert build_portfolio_timeseries(tx, prices).iloc[-1]["value"] == pytest.approx(10)


def test_holding_before_first_price_raises() -> None:
    tx = pd.DataFrame([_tx("2025-01-06", "ABC", "BUY", 1, 10)])
    prices = pd.DataFrame({"ABC": [10]}, index=_days("2025-01-08"))
    with pytest.raises(ValueError, match="without a price"):
        build_portfolio_timeseries(tx, prices)


def test_unknown_transaction_type_raises() -> None:
    tx = pd.DataFrame([_tx("2025-01-06", "ABC", "DIVIDEND", 1, 10)])
    prices = pd.DataFrame({"ABC": [10]}, index=_days("2025-01-06"))
    with pytest.raises(ValueError, match="Unknown transaction types"):
        build_portfolio_timeseries(tx, prices)

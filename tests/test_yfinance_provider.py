from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trackfolio.market_data.yfinance_provider import TIMEOUT_SECONDS, YFinanceProvider

MODULE = "trackfolio.market_data.yfinance_provider.yf"


def test_history_normalizes_timezone_and_passes_timeout() -> None:
    index = pd.DatetimeIndex(["2024-01-02 00:00", "2024-01-03 00:00"], tz="America/New_York")
    frame = pd.DataFrame({"Close": [10.0, None]}, index=index)
    with patch(MODULE) as yf:
        yf.Ticker.return_value.history.return_value = frame
        closes = YFinanceProvider().get_history("aapl", date(2024, 1, 1), date(2024, 1, 5))
    assert yf.Ticker.return_value.history.call_args.kwargs["timeout"] == TIMEOUT_SECONDS
    assert closes.index.tz is None
    assert list(closes.index) == [pd.Timestamp("2024-01-02")]
    assert closes.name == "AAPL"


def test_history_empty_raises_value_error() -> None:
    with patch(MODULE) as yf:
        yf.Ticker.return_value.history.return_value = pd.DataFrame()
        with pytest.raises(ValueError, match="No price history"):
            YFinanceProvider().get_history("AAPL", date(2024, 1, 1), date(2024, 1, 5))


def test_history_wraps_unexpected_errors() -> None:
    with patch(MODULE) as yf:
        yf.Ticker.return_value.history.side_effect = KeyError("boom")
        with pytest.raises(RuntimeError, match="history request failed"):
            YFinanceProvider().get_history("AAPL", date(2024, 1, 1), date(2024, 1, 5))


def test_get_asset_maps_info_and_rejects_unknown() -> None:
    with patch(MODULE) as yf:
        yf.Ticker.return_value.get_info.return_value = {
            "currency": "usd",
            "longName": "Apple Inc.",
            "exchange": "NMS",
            "quoteType": "EQUITY",
        }
        asset = YFinanceProvider().get_asset(" aapl ")
        assert (asset.ticker, asset.currency, asset.name) == ("AAPL", "USD", "Apple Inc.")
        yf.Ticker.return_value.get_info.return_value = {}
        with pytest.raises(ValueError, match="does not recognize"):
            YFinanceProvider().get_asset("NOPE")
        yf.Ticker.return_value.get_info.side_effect = ConnectionError("down")
        with pytest.raises(RuntimeError, match="lookup failed"):
            YFinanceProvider().get_asset("AAPL")


def test_search_uses_timeout_and_falls_back_to_quote_data() -> None:
    quotes = [
        {"symbol": "abc", "longname": "ABC Corp", "currency": "eur", "exchDisp": "Milan"},
        {"symbol": "nocur"},
        {"currency": "USD"},
    ]
    with patch(MODULE) as yf:
        yf.Search.return_value = MagicMock(quotes=quotes)
        yf.Ticker.return_value.get_info.return_value = {}
        assets = YFinanceProvider().search_tickers("abc")
    assert yf.Search.call_args.kwargs["timeout"] == TIMEOUT_SECONDS
    assert [(a.ticker, a.currency, a.exchange) for a in assets] == [("ABC", "EUR", "Milan")]


def test_search_wraps_errors() -> None:
    with patch(MODULE) as yf:
        yf.Search.side_effect = OSError("down")
        with pytest.raises(RuntimeError, match="search failed"):
            YFinanceProvider().search_tickers("abc")

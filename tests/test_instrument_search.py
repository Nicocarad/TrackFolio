import json
from datetime import date
from io import BytesIO
from unittest.mock import patch

import pandas as pd
import pytest

from trackfolio.market_data.instrument_search import OPENFIGI_URL, search_isin
from trackfolio.models import Asset


class UnusedProvider:
    def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
        raise AssertionError("Invalid ISIN must be rejected before network access")

    def get_asset(self, ticker: str) -> Asset:
        raise AssertionError("Invalid ISIN must be rejected before network access")

    def search_tickers(self, query: str) -> list[Asset]:
        raise AssertionError("Invalid ISIN must be rejected before network access")


def test_invalid_isin_is_rejected_before_network_request() -> None:
    with pytest.raises(ValueError, match="ISIN is invalid"):
        search_isin("US0378331004", provider=UnusedProvider())


def test_valid_isin_resolves_to_provider_listing() -> None:
    class SearchProvider(UnusedProvider):
        def search_tickers(self, query: str) -> list[Asset]:
            return [Asset(ticker="AAPL", name="Apple Inc.", currency="USD", isin=query)]

    mapping = [{"data": [{"ticker": "AAPL", "name": "Apple Inc."}]}]
    response = BytesIO(json.dumps(mapping).encode("utf-8"))
    with patch(
        "trackfolio.market_data.instrument_search.urllib.request.urlopen", return_value=response
    ) as open_url:
        results = search_isin("US0378331005", SearchProvider())

    open_url.assert_called_once()
    assert open_url.call_args.args[0].full_url == OPENFIGI_URL
    assert [(asset.ticker, asset.currency, asset.isin) for asset in results] == [
        ("AAPL", "USD", "US0378331005")
    ]

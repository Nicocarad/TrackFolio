import json
import urllib.error
from datetime import date
from email.message import Message
from io import BytesIO
from unittest.mock import patch

import pandas as pd
import pytest

from trackfolio.market_data.instrument_search import OPENFIGI_URL, search_isin, search_ticker
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


ISIN = "US0378331005"
MODULE = "trackfolio.market_data.instrument_search"


class FakeProvider(UnusedProvider):
    def __init__(self, found: list[Asset] | None = None, error: Exception | None = None) -> None:
        self.found = found or []
        self.error = error
        self.queries: list[str] = []

    def search_tickers(self, query: str) -> list[Asset]:
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.found


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(OPENFIGI_URL, code, "err", headers, None)


def _ok(payload: object) -> BytesIO:
    return BytesIO(json.dumps(payload).encode("utf-8"))


def _aapl() -> Asset:
    return Asset(ticker="AAPL", name="Apple Inc.", currency="USD")


def test_urlerror_falls_back_to_yahoo_and_stamps_isin() -> None:
    provider = FakeProvider([_aapl()])
    with patch(f"{MODULE}.urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        results = search_isin(ISIN, provider)
    assert provider.queries == [ISIN]
    assert [a.isin for a in results] == [ISIN]


@pytest.mark.parametrize("payload", [[{"data": []}], [{"warning": "No identifier found."}], []])
def test_empty_data_falls_back_to_yahoo(payload: object) -> None:
    provider = FakeProvider([_aapl()])
    with patch(f"{MODULE}.urllib.request.urlopen", return_value=_ok(payload)):
        results = search_isin(ISIN, provider)
    assert [a.ticker for a in results] == ["AAPL"]


@pytest.mark.parametrize("payload", [{"data": 1}, [1], "x", [{"data": "AAPL"}], [{"data": [1]}]])
def test_unexpected_payload_shapes_do_not_crash(payload: object) -> None:
    provider = FakeProvider([_aapl()])
    with patch(f"{MODULE}.urllib.request.urlopen", return_value=_ok(payload)):
        results = search_isin(ISIN, provider)
    assert [a.ticker for a in results] == ["AAPL"]


def test_malformed_json_falls_back_to_yahoo() -> None:
    provider = FakeProvider([_aapl()])
    with patch(f"{MODULE}.urllib.request.urlopen", return_value=BytesIO(b"not json")):
        assert search_isin(ISIN, provider)[0].ticker == "AAPL"


def test_double_failure_raises_runtime_error() -> None:
    provider = FakeProvider(error=RuntimeError("yahoo down"))
    with patch(f"{MODULE}.urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        with pytest.raises(RuntimeError, match="Yahoo fallback failed"):
            search_isin(ISIN, provider)


def test_empty_data_with_failing_yahoo_is_wrapped() -> None:
    provider = FakeProvider(error=RuntimeError("yahoo down"))
    with patch(f"{MODULE}.urllib.request.urlopen", return_value=_ok([{"data": []}])):
        with pytest.raises(RuntimeError, match="Yahoo fallback failed"):
            search_isin(ISIN, provider)


def test_429_retries_honoring_retry_after_then_succeeds() -> None:
    provider = FakeProvider([_aapl()])
    responses = [_http_error(429, "7"), _ok([{"data": [{"ticker": "AAPL", "name": "Apple"}]}])]
    with (
        patch(f"{MODULE}.urllib.request.urlopen", side_effect=responses) as open_url,
        patch(f"{MODULE}.time.sleep") as sleep,
    ):
        results = search_isin(ISIN, provider)
    assert open_url.call_count == 2
    sleep.assert_called_once_with(7.0)
    assert results[0].isin == ISIN


def test_persistent_429_raises_without_yahoo_fallback() -> None:
    provider = FakeProvider([_aapl()])
    with (
        patch(f"{MODULE}.urllib.request.urlopen", side_effect=lambda *a, **k: _raise(429)),
        patch(f"{MODULE}.time.sleep"),
    ):
        with pytest.raises(RuntimeError, match="429"):
            search_isin(ISIN, provider)
    assert provider.queries == []


def _raise(code: int) -> None:
    raise _http_error(code)


def test_persistent_5xx_retries_then_falls_back() -> None:
    provider = FakeProvider([_aapl()])
    with (
        patch(f"{MODULE}.urllib.request.urlopen", side_effect=lambda *a, **k: _raise(503)) as o,
        patch(f"{MODULE}.time.sleep"),
    ):
        results = search_isin(ISIN, provider)
    assert o.call_count == 3
    assert provider.queries == [ISIN]
    assert results[0].isin == ISIN


def test_other_4xx_is_not_retried() -> None:
    provider = FakeProvider([_aapl()])
    with (
        patch(f"{MODULE}.urllib.request.urlopen", side_effect=lambda *a, **k: _raise(400)) as o,
        patch(f"{MODULE}.time.sleep") as sleep,
    ):
        search_isin(ISIN, provider)
    assert o.call_count == 1
    sleep.assert_not_called()


def test_api_key_header_sent_only_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeProvider([_aapl()])
    monkeypatch.setenv("OPENFIGI_API_KEY", "secret")
    with patch(f"{MODULE}.urllib.request.urlopen", return_value=_ok([{"data": []}])) as o:
        search_isin(ISIN, provider)
    assert o.call_args.args[0].get_header("X-openfigi-apikey") == "secret"
    monkeypatch.delenv("OPENFIGI_API_KEY")
    with patch(f"{MODULE}.urllib.request.urlopen", return_value=_ok([{"data": []}])) as o:
        search_isin(ISIN, provider)
    assert not o.call_args.args[0].has_header("X-openfigi-apikey")


def test_isin_stamped_only_on_figi_matched_candidates() -> None:
    class NameSearch(FakeProvider):
        def search_tickers(self, query: str) -> list[Asset]:
            return [
                _aapl(),
                Asset(ticker="AAPL.MI", name="Apple Milan", currency="EUR"),
                Asset(ticker="XYZ", name="Unrelated", currency="USD"),
            ]

    mapping = [{"data": [{"ticker": "AAPL", "name": "Apple"}]}]
    with patch(f"{MODULE}.urllib.request.urlopen", return_value=_ok(mapping)):
        results = {a.ticker: a.isin for a in search_isin(ISIN, NameSearch())}
    assert results == {"AAPL": ISIN, "AAPL.MI": ISIN, "XYZ": None}


def test_search_ticker_rejects_blank_query() -> None:
    with pytest.raises(ValueError, match="Enter an ISIN or ticker"):
        search_ticker("  ", UnusedProvider())

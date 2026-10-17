"""ISIN validation and instrument lookup."""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from stdnum import isin

from trackfolio.market_data.provider import PriceProvider
from trackfolio.models import Asset

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
API_KEY_ENV = "OPENFIGI_API_KEY"
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY = 30.0
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class RateLimitedError(RuntimeError):
    """OpenFIGI kept answering 429 after all retries."""


def _retry_delay(error: urllib.error.HTTPError, attempt: int) -> float:
    """Seconds to wait: Retry-After when numeric, else exponential backoff, capped."""
    header = error.headers.get("Retry-After") if error.headers else None
    try:
        delay = float(header) if header is not None else 2.0**attempt
    except ValueError:
        delay = 2.0**attempt
    return min(max(delay, 0.0), MAX_RETRY_DELAY)


def _post_openfigi(normalized: str) -> Any:
    """POST one ISIN mapping, retrying on 429/5xx. Raises URLError, HTTPError or ValueError."""
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get(API_KEY_ENV)
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key
    body = json.dumps([{"idType": "ID_ISIN", "idValue": normalized}]).encode("utf-8")
    for attempt in range(MAX_ATTEMPTS):
        request = urllib.request.Request(OPENFIGI_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code not in _RETRY_STATUSES:
                raise
            if attempt == MAX_ATTEMPTS - 1:
                if error.code == 429:
                    raise RateLimitedError("OpenFIGI rate limit exceeded (HTTP 429)") from error
                raise
            time.sleep(_retry_delay(error, attempt))
    raise AssertionError("unreachable")  # pragma: no cover


def _mapped_items(payload: Any) -> list[dict[str, Any]]:
    """Extract the mapping entries from an OpenFIGI response, tolerating odd shapes."""
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return []
    data = payload[0].get("data")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _yahoo_by_isin(normalized: str, provider: PriceProvider, reason: str) -> list[Asset]:
    """Search Yahoo for the ISIN itself; those hits are ISIN-matched, so stamp them."""
    try:
        return [
            asset.model_copy(update={"isin": normalized})
            for asset in provider.search_tickers(normalized)
        ]
    except (ValueError, RuntimeError) as fallback_error:
        raise RuntimeError(
            f"{reason}; Yahoo fallback failed ({fallback_error})"
        ) from fallback_error


def search_isin(isin_value: str, provider: PriceProvider) -> list[Asset]:
    """Find Yahoo-compatible listings for a valid ISIN via OpenFIGI and Yahoo Search.

    OpenFIGI 429s are raised, not hidden behind the Yahoo fallback. The ISIN is stamped
    only on candidates whose ticker OpenFIGI mapped to it, or found by searching the ISIN.
    """
    normalized = isin_value.strip().upper()
    if not isin.is_valid(normalized):
        raise ValueError("ISIN is invalid (format or check digit)")

    try:
        payload = _post_openfigi(normalized)
    except RateLimitedError:
        raise
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        return _yahoo_by_isin(normalized, provider, f"OpenFIGI lookup failed ({error})")

    mapped = _mapped_items(payload)
    if not mapped:
        return _yahoo_by_isin(normalized, provider, "OpenFIGI returned no match")

    figi_tickers = {
        str(item["ticker"]).strip().upper()
        for item in mapped
        if isinstance(item.get("ticker"), str) and item["ticker"].strip()
    }
    search_terms = list(
        dict.fromkeys(
            value.strip()
            for item in mapped
            for key in ("name", "ticker")
            if isinstance(value := item.get(key), str) and value.strip()
        )
    )
    candidates: dict[str, Asset] = {}
    for term in search_terms[:5]:
        for asset in provider.search_tickers(term):
            # A name search can return unrelated instruments; stamp only the mapped tickers.
            matched = asset.ticker.split(".")[0] in figi_tickers or asset.ticker in figi_tickers
            candidates.setdefault(
                asset.ticker, asset.model_copy(update={"isin": normalized}) if matched else asset
            )
    for ticker in sorted(figi_tickers - candidates.keys()):
        try:
            asset = provider.get_asset(ticker)
        except ValueError, RuntimeError:
            continue
        candidates[ticker] = asset.model_copy(update={"isin": normalized})
    return list(candidates.values())


def search_ticker(query: str, provider: PriceProvider) -> list[Asset]:
    """Search by name or ticker using Yahoo Finance."""
    normalized = query.strip()
    if not normalized:
        raise ValueError("Enter an ISIN or ticker")
    return provider.search_tickers(normalized)

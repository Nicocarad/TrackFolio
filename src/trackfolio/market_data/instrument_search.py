"""ISIN validation and instrument lookup."""

import json
import urllib.error
import urllib.request

from stdnum import isin

from trackfolio.market_data.provider import PriceProvider
from trackfolio.models import Asset

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


def search_isin(isin_value: str, provider: PriceProvider) -> list[Asset]:
    """Find Yahoo-compatible listings for a valid ISIN via OpenFIGI and Yahoo Search."""
    normalized = isin_value.strip().upper()
    if not isin.is_valid(normalized):
        raise ValueError("ISIN is invalid (format or check digit)")

    request = urllib.request.Request(
        OPENFIGI_URL,
        data=json.dumps([{"idType": "ID_ISIN", "idValue": normalized}]).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        try:
            return [
                asset.model_copy(update={"isin": normalized})
                for asset in provider.search_tickers(normalized)
            ]
        except (ValueError, RuntimeError) as fallback_error:
            raise RuntimeError(
                f"OpenFIGI lookup failed ({error}); Yahoo fallback failed ({fallback_error})"
            ) from fallback_error

    mapped = payload[0].get("data", []) if payload and isinstance(payload[0], dict) else []
    if not mapped:
        return [
            asset.model_copy(update={"isin": normalized})
            for asset in provider.search_tickers(normalized)
        ]
    search_terms = list(
        dict.fromkeys(
            str(item.get(key, "")).strip()
            for item in mapped
            for key in ("name", "ticker")
            if item.get(key)
        )
    )
    candidates: dict[str, Asset] = {}
    for term in search_terms[:5]:
        for asset in provider.search_tickers(term):
            candidates.setdefault(asset.ticker, asset.model_copy(update={"isin": normalized}))
    for item in mapped:
        ticker = str(item.get("ticker", "")).strip().upper()
        if not ticker or ticker in candidates:
            continue
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

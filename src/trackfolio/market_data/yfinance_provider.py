"""Yahoo Finance implementation of the market-data contract."""

from datetime import date

import pandas as pd
import yfinance as yf

from trackfolio.models import Asset


class YFinanceProvider:
    """Fetch daily closes and instrument metadata from Yahoo Finance."""

    def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
        """Return daily closing prices, raising when Yahoo returns no history."""
        history = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=False,
            actions=False,
        )
        if history.empty or "Close" not in history:
            raise ValueError(f"No price history returned for {ticker}")
        closes = history["Close"].dropna().astype("float64")
        closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
        closes.name = ticker.upper()
        return closes

    def get_asset(self, ticker: str) -> Asset:
        """Resolve a ticker using Yahoo Finance instrument metadata."""
        symbol = ticker.strip().upper()
        info = yf.Ticker(symbol).get_info()
        if not info or not info.get("currency"):
            raise ValueError(f"Yahoo Finance does not recognize ticker {symbol}")
        return Asset(
            ticker=symbol,
            name=str(info.get("longName") or info.get("shortName") or symbol),
            currency=str(info["currency"]).upper(),
            exchange=str(info.get("exchange") or "") or None,
            asset_class=str(info.get("quoteType") or "") or None,
        )

    def search_tickers(self, query: str) -> list[Asset]:
        """Search Yahoo Finance symbols by name or ticker."""
        response = yf.Search(query, max_results=10)
        assets: dict[str, Asset] = {}
        for quote in response.quotes:
            symbol = quote.get("symbol")
            if not symbol:
                continue
            normalized = str(symbol).upper()
            try:
                asset = self.get_asset(normalized)
            except ValueError:
                currency = quote.get("currency")
                if not currency:
                    continue
                asset = Asset(
                    ticker=normalized,
                    name=str(quote.get("longname") or quote.get("shortname") or symbol),
                    currency=str(currency).upper(),
                    exchange=str(quote.get("exchDisp") or "") or None,
                    asset_class=str(quote.get("quoteType") or "") or None,
                )
            assets.setdefault(normalized, asset)
        return list(assets.values())

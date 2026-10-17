"""Market-data provider contract."""

from datetime import date
from typing import Protocol

import pandas as pd

from trackfolio.models import Asset


class PriceProvider(Protocol):
    """Interface implemented by market data sources."""

    def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
        """Return daily closing prices for a ticker."""

    def get_asset(self, ticker: str) -> Asset:
        """Resolve a provider ticker to instrument metadata."""

    def search_tickers(self, query: str) -> list[Asset]:
        """Search provider tickers by name or symbol."""

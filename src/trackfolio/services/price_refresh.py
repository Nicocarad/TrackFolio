"""Shared price refresh: one provider call per held ticker, whoever holds it."""

import logging
from datetime import date, timedelta

from sqlmodel import Session

from trackfolio.market_data.provider import PriceProvider
from trackfolio.repositories import assets, prices, transactions
from trackfolio.services.warnings import DataWarning, WarningCode

logger = logging.getLogger(__name__)
REFRESH_OVERLAP_DAYS = 5


def _first_dates(session: Session) -> dict[str, date]:
    """First date each ticker, and each FX pair needed for it, must have prices from."""
    asset_currency = {a.ticker: a.currency.upper() for a in assets.get_assets(session)}
    needed: dict[str, date] = {}
    for transaction in transactions.list_all_transactions(session):
        series = [transaction.ticker]
        currency = asset_currency.get(transaction.ticker)
        if currency and currency != "EUR":
            series.append(f"EUR{currency}=X")
        for name in series:
            needed[name] = min(needed.get(name, transaction.date), transaction.date)
    return needed


def refresh_all_prices(session: Session, provider: PriceProvider) -> tuple[int, list[DataWarning]]:
    """Refresh cached asset and FX prices for every user's holdings.

    A failing ticker keeps its cache and is reported; the others are still refreshed.
    """
    end = date.today() + timedelta(days=1)
    warnings: list[DataWarning] = []
    saved = 0
    for ticker, first_trade in sorted(_first_dates(session).items()):
        try:
            cached = prices.get_prices(session, ticker)
            start = first_trade
            if not cached.empty and cached.index.min().date() <= first_trade + timedelta(days=7):
                start = cached.index.max().date() - timedelta(days=REFRESH_OVERLAP_DAYS)
            history = provider.get_history(ticker, start, end)
            prices.save_prices(session, ticker, history)
            session.commit()
            saved += len(history.dropna())
        except Exception as error:
            session.rollback()
            logger.warning("Price refresh failed for %s: %s", ticker, error)
            cached = prices.get_prices(session, ticker)
            until = None if cached.empty else cached.index.max().date()
            warnings.append(DataWarning(WarningCode.REFRESH_FAILED, ticker, str(error), until))
    return saved, warnings

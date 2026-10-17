"""Portfolio use cases coordinating persistence, market data, and pure calculations."""

import logging
from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session

from trackfolio.core.holdings import build_holdings
from trackfolio.core.metrics import PortfolioMetrics, calculate_metrics
from trackfolio.core.positions import calculate_positions, validate_transaction
from trackfolio.core.returns import twr_pct, xirr_pct
from trackfolio.core.timeseries import build_portfolio_timeseries
from trackfolio.market_data.provider import PriceProvider
from trackfolio.models import Asset, Transaction
from trackfolio.repositories import assets, prices, transactions

logger = logging.getLogger(__name__)
REFRESH_OVERLAP_DAYS = 5


def _check_currency(transaction: Transaction, asset: Asset) -> None:
    if transaction.currency.upper() != asset.currency.upper():
        raise ValueError(
            f"Transaction currency {transaction.currency} does not match "
            f"{transaction.ticker} currency {asset.currency}"
        )


class PortfolioService:
    """Application boundary used by the UI."""

    def __init__(self, session: Session, provider: PriceProvider) -> None:
        self.session = session
        self.provider = provider

    def list_transactions(self) -> list[Transaction]:
        """List all saved transactions."""
        return transactions.list_transactions(self.session)

    def save_transaction(self, transaction: Transaction, asset: Asset | None = None) -> Transaction:
        """Validate holdings and asset, then insert or update a transaction atomically.

        ``asset`` is the instrument to register when the ticker is not stored yet; if omitted
        it is fetched from the provider.
        """
        try:
            existing = transactions.list_transactions(self.session)
            data = transaction.model_dump()
            validate_transaction(
                data, pd.DataFrame([item.model_dump() for item in existing]), transaction.id
            )
            proposed = [item.model_dump() for item in existing if item.id != transaction.id]
            proposed.append(data)
            calculate_positions(pd.DataFrame(proposed))
            known = assets.get_asset(self.session, transaction.ticker)
            if known is None:
                known = asset or self.provider.get_asset(transaction.ticker)
                _check_currency(transaction, known)
                assets.save_asset(self.session, known)
            else:
                _check_currency(transaction, known)
            saved = transactions.save_transaction(self.session, transaction)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(saved)
        return saved

    def delete_transaction(self, transaction_id: int) -> None:
        """Delete a transaction."""
        current = transactions.list_transactions(self.session)
        proposed = [item.model_dump() for item in current if item.id != transaction_id]
        if len(proposed) == len(current):
            raise ValueError(f"Transaction {transaction_id} does not exist")
        calculate_positions(pd.DataFrame(proposed))
        try:
            transactions.delete_transaction(self.session, transaction_id)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _assets_by_ticker(self) -> dict[str, Asset | None]:
        stored = {asset.ticker: asset for asset in assets.get_assets(self.session)}
        tickers = {item.ticker for item in transactions.list_transactions(self.session)}
        return {ticker: stored.get(ticker) for ticker in tickers}

    def refresh_prices(self) -> tuple[int, list[str]]:
        """Refresh cached asset and FX prices, retaining cache on provider failures."""
        all_transactions = transactions.list_transactions(self.session)
        if not all_transactions:
            return 0, []
        tickers = sorted({item.ticker for item in all_transactions})
        asset_map = self._assets_by_ticker()
        currencies = {item.currency.upper() for item in asset_map.values() if item is not None}
        fx_tickers = [f"EUR{currency}=X" for currency in currencies if currency != "EUR"]
        requested = tickers + fx_tickers
        first_trade = min(item.date for item in all_transactions)
        end = date.today() + timedelta(days=1)
        warnings: list[str] = []
        saved = 0
        for ticker in requested:
            try:
                cached = prices.get_prices(self.session, ticker)
                start = first_trade
                if not cached.empty and cached.index.min().date() <= first_trade + timedelta(
                    days=7
                ):
                    start = cached.index.max().date() - timedelta(days=REFRESH_OVERLAP_DAYS)
                history = self.provider.get_history(ticker, start, end)
                prices.save_prices(self.session, ticker, history)
                self.session.commit()
                saved += len(history.dropna())
            except Exception as error:
                self.session.rollback()
                logger.warning("Price refresh failed for %s: %s", ticker, error)
                cached = prices.get_prices(self.session, ticker)
                if cached.empty:
                    warnings.append(f"{ticker}: aggiornamento fallito e cache assente ({error})")
                else:
                    warnings.append(
                        f"{ticker}: aggiornamento fallito; uso cache fino al "
                        f"{cached.index.max().date()} ({error})"
                    )
        return saved, warnings

    def dashboard_data(
        self,
    ) -> tuple[pd.DataFrame, pd.DataFrame, PortfolioMetrics, list[str]]:
        """Return historical valuation, current positions, KPIs, and data warnings."""
        tx_models = transactions.list_transactions(self.session)
        if not tx_models:
            empty = pd.DataFrame()
            return empty, empty, calculate_metrics(0, 0), []

        tx = pd.DataFrame([item.model_dump() for item in tx_models])
        asset_map = self._assets_by_ticker()
        tickers = sorted(set(tx["ticker"]))
        local_prices: dict[str, pd.Series] = {}
        warnings: list[str] = []
        for ticker in tickers:
            cached = prices.get_prices(self.session, ticker)
            if cached.empty:
                warnings.append(f"Nessun prezzo in cache per {ticker}")
            else:
                local_prices[ticker] = cached
        if len(local_prices) != len(tickers):
            return pd.DataFrame(), pd.DataFrame(), calculate_metrics(0, 0), warnings
        price_frame = pd.concat(local_prices.values(), axis=1).sort_index()
        currencies = {asset.currency.upper() for asset in asset_map.values() if asset is not None}
        fx = pd.DataFrame(index=price_frame.index)
        fx["EUR"] = 1.0
        for currency in currencies - {"EUR"}:
            ticker = f"EUR{currency}=X"
            cached = prices.get_prices(self.session, ticker)
            if cached.empty:
                warnings.append(f"Nessun tasso di cambio in cache per {currency}/EUR")
                continue
            fx[currency] = 1 / cached.reindex(price_frame.index).ffill().replace(0, float("nan"))
        if warnings:
            return pd.DataFrame(), pd.DataFrame(), calculate_metrics(0, 0), warnings
        asset_currencies = {
            ticker: asset.currency.upper() for ticker, asset in asset_map.items() if asset
        }
        try:
            history = build_portfolio_timeseries(tx, price_frame, fx, asset_currencies)
        except ValueError as error:
            warnings.append(str(error))
            return pd.DataFrame(), pd.DataFrame(), calculate_metrics(0, 0), warnings
        asset_info = {t: (a.name, a.currency.upper()) for t, a in asset_map.items() if a}
        holdings = build_holdings(calculate_positions(tx), price_frame, fx, asset_info)
        latest = history.iloc[-1]
        metrics = calculate_metrics(
            float(latest["value"]),
            float(latest["invested_capital"]),
            twr_pct(history),
            xirr_pct(history),
        )
        return history, holdings, metrics, warnings

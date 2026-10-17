"""Portfolio use cases coordinating persistence, market data, and pure calculations."""

import logging
from datetime import date

import pandas as pd
from sqlmodel import Session
from stdnum import isin as stdnum_isin

from trackfolio.core.holdings import build_holdings
from trackfolio.core.metrics import PortfolioMetrics, calculate_metrics
from trackfolio.core.positions import calculate_positions, validate_transaction
from trackfolio.core.returns import period_returns_pct, twr_pct, xirr_pct
from trackfolio.core.timeseries import build_portfolio_timeseries
from trackfolio.errors import DomainError, ErrorCode
from trackfolio.market_data.instrument_search import search_isin, search_ticker
from trackfolio.market_data.provider import PriceProvider
from trackfolio.models import Asset, Transaction
from trackfolio.repositories import assets, prices, transactions
from trackfolio.services.warnings import DataWarning, WarningCode

logger = logging.getLogger(__name__)


class PortfolioService:
    """Application boundary used by the web layer; every operation is scoped to one user."""

    def __init__(self, session: Session, provider: PriceProvider, user_id: int) -> None:
        self.session = session
        self.user_id = user_id
        self.provider = provider

    def list_transactions(self) -> list[Transaction]:
        """List all saved transactions."""
        return transactions.list_transactions(self.session, self.user_id)

    def save_transaction(self, transaction: Transaction, isin: str | None = None) -> Transaction:
        """Validate holdings and asset, then insert or update a transaction atomically.

        ``isin`` is recorded on the asset when the ticker is not stored yet (the provider
        metadata does not carry it).
        """
        try:
            existing = transactions.list_transactions(self.session, self.user_id)
            data = transaction.model_dump()
            validate_transaction(
                data, pd.DataFrame([item.model_dump() for item in existing]), transaction.id
            )
            proposed = [item.model_dump() for item in existing if item.id != transaction.id]
            proposed.append(data)
            calculate_positions(pd.DataFrame(proposed))
            known = assets.get_asset(self.session, transaction.ticker)
            if known is None:
                known = self.provider.get_asset(transaction.ticker)
                if isin and stdnum_isin.is_valid(isin.upper()):
                    known.isin = isin.upper()
                assets.save_asset(self.session, known)
            saved = transactions.save_transaction(self.session, self.user_id, transaction)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(saved)
        return saved

    def delete_transaction(self, transaction_id: int) -> None:
        """Delete a transaction."""
        current = transactions.list_transactions(self.session, self.user_id)
        proposed = [item.model_dump() for item in current if item.id != transaction_id]
        if len(proposed) == len(current):
            raise DomainError(ErrorCode.TRANSACTION_NOT_FOUND, transaction_id=transaction_id)
        calculate_positions(pd.DataFrame(proposed))
        try:
            transactions.delete_transaction(self.session, self.user_id, transaction_id)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def last_price_date(self) -> date | None:
        """Most recent cached market-data date."""
        return prices.latest_price_date(self.session)

    def search_instrument(self, query: str) -> list[Asset]:
        """Find listings by ISIN (auto-detected) or ticker/name."""
        normalized = query.strip()
        if stdnum_isin.is_valid(normalized.upper()):
            return search_isin(normalized, self.provider)
        return search_ticker(normalized, self.provider)

    def asset_currencies(self) -> dict[str, str]:
        """Map every known ticker to its currency."""
        return {asset.ticker: asset.currency.upper() for asset in assets.get_assets(self.session)}

    def _assets_by_ticker(self) -> dict[str, Asset | None]:
        stored = {asset.ticker: asset for asset in assets.get_assets(self.session)}
        tickers = {
            item.ticker for item in transactions.list_transactions(self.session, self.user_id)
        }
        return {ticker: stored.get(ticker) for ticker in tickers}

    def dashboard_data(
        self,
    ) -> tuple[pd.DataFrame, pd.DataFrame, PortfolioMetrics, list[DataWarning]]:
        """Return historical valuation, current positions, KPIs, and data warnings."""
        tx_models = transactions.list_transactions(self.session, self.user_id)
        if not tx_models:
            empty = pd.DataFrame()
            return empty, empty, calculate_metrics(0, 0), []

        tx = pd.DataFrame([item.model_dump() for item in tx_models])
        asset_map = self._assets_by_ticker()
        tickers = sorted(set(tx["ticker"]))
        local_prices: dict[str, pd.Series] = {}
        excluded: list[str] = []
        warnings: list[DataWarning] = []
        for ticker in tickers:
            cached = prices.get_prices(self.session, ticker)
            if cached.empty:
                warnings.append(DataWarning(WarningCode.NO_PRICE, ticker))
                excluded.append(ticker)
            else:
                local_prices[ticker] = cached
        ticker_currency = {t: a.currency.upper() for t, a in asset_map.items() if a}
        rates: dict[str, pd.Series] = {}
        for currency in set(ticker_currency.values()) - {"EUR"}:
            cached = prices.get_prices(self.session, f"EUR{currency}=X")
            if cached.empty:
                warnings.append(DataWarning(WarningCode.NO_FX, currency))
                excluded += [t for t in local_prices if ticker_currency.get(t) == currency]
            else:
                rates[currency] = cached
        for ticker in excluded:
            local_prices.pop(ticker, None)
        if not local_prices:
            return pd.DataFrame(), pd.DataFrame(), calculate_metrics(0, 0), warnings
        if excluded:
            warnings.append(DataWarning(WarningCode.EXCLUDED, ", ".join(sorted(set(excluded)))))
            tx = tx[tx["ticker"].isin(local_prices)]
        price_frame = pd.concat(local_prices.values(), axis=1).sort_index()
        fx = pd.DataFrame(index=price_frame.index)
        fx["EUR"] = 1.0
        for currency, cached in rates.items():
            fx[currency] = 1 / cached.reindex(price_frame.index).ffill().replace(0, float("nan"))
        asset_currencies = {
            ticker: asset.currency.upper() for ticker, asset in asset_map.items() if asset
        }
        try:
            history = build_portfolio_timeseries(tx, price_frame, asset_currencies, fx)
        except ValueError as error:
            domain_error = error if isinstance(error, DomainError) else None
            warnings.append(
                DataWarning(WarningCode.DATA_ERROR, detail=str(error), error=domain_error)
            )
            return pd.DataFrame(), pd.DataFrame(), calculate_metrics(0, 0), warnings
        asset_info = {t: (a.name, a.currency.upper()) for t, a in asset_map.items() if a}
        holdings = build_holdings(calculate_positions(tx), price_frame, fx, asset_info)
        latest = history.iloc[-1]
        metrics = calculate_metrics(
            float(latest["value"]),
            float(latest["invested_capital"]),
            twr_pct(history),
            xirr_pct(history),
            period_returns_pct(history),
        )
        return history, holdings, metrics, warnings

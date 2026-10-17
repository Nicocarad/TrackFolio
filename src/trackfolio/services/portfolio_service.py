"""Portfolio use cases coordinating persistence, market data, and pure calculations."""

from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session

from trackfolio.core.metrics import PortfolioMetrics, calculate_metrics
from trackfolio.core.positions import calculate_positions, validate_transaction
from trackfolio.core.timeseries import build_portfolio_timeseries
from trackfolio.market_data.provider import PriceProvider
from trackfolio.models import Transaction
from trackfolio.repositories import assets, prices, transactions


class PortfolioService:
    """Application boundary used by the UI."""

    def __init__(self, session: Session, provider: PriceProvider) -> None:
        self.session = session
        self.provider = provider

    def list_transactions(self) -> list[Transaction]:
        """List all saved transactions."""
        return transactions.list_transactions(self.session)

    def save_transaction(self, transaction: Transaction) -> Transaction:
        """Validate holdings and asset, then insert or update a transaction."""
        existing = transactions.list_transactions(self.session)
        data = transaction.model_dump()
        validate_transaction(
            data, pd.DataFrame([item.model_dump() for item in existing]), transaction.id
        )
        proposed = [item.model_dump() for item in existing if item.id != transaction.id]
        proposed.append(data)
        calculate_positions(pd.DataFrame(proposed))
        asset = assets.get_asset(self.session, transaction.ticker)
        if asset is None:
            asset = self.provider.get_asset(transaction.ticker)
            if transaction.currency.upper() != asset.currency.upper():
                raise ValueError(
                    f"Transaction currency {transaction.currency} does not match "
                    f"{transaction.ticker} currency {asset.currency}"
                )
            assets.save_asset(self.session, asset)
        elif transaction.currency.upper() != asset.currency.upper():
            raise ValueError(
                f"Transaction currency {transaction.currency} does not match "
                f"{transaction.ticker} currency {asset.currency}"
            )
        return transactions.save_transaction(self.session, transaction)

    def delete_transaction(self, transaction_id: int) -> None:
        """Delete a transaction."""
        current = transactions.list_transactions(self.session)
        proposed = [item.model_dump() for item in current if item.id != transaction_id]
        if len(proposed) == len(current):
            raise ValueError(f"Transaction {transaction_id} does not exist")
        calculate_positions(pd.DataFrame(proposed))
        transactions.delete_transaction(self.session, transaction_id)

    def refresh_prices(self) -> tuple[int, list[str]]:
        """Refresh cached asset and FX prices, retaining cache on provider failures."""
        all_transactions = transactions.list_transactions(self.session)
        if not all_transactions:
            return 0, []
        tickers = sorted({item.ticker for item in all_transactions})
        asset_map = {ticker: assets.get_asset(self.session, ticker) for ticker in tickers}
        currencies = {item.currency.upper() for item in asset_map.values() if item is not None}
        fx_tickers = [f"EUR{currency}=X" for currency in currencies if currency != "EUR"]
        requested = tickers + fx_tickers
        start = min(item.date for item in all_transactions)
        end = date.today() + timedelta(days=1)
        warnings: list[str] = []
        saved = 0
        for ticker in requested:
            try:
                history = self.provider.get_history(ticker, start, end)
                prices.save_prices(self.session, ticker, history)
                saved += len(history.dropna())
            except (ValueError, RuntimeError, TimeoutError) as error:
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
        asset_map = {item.ticker: assets.get_asset(self.session, item.ticker) for item in tx_models}
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
            fx[currency] = 1 / cached.reindex(price_frame.index).ffill()
        if warnings:
            return pd.DataFrame(), pd.DataFrame(), calculate_metrics(0, 0), warnings
        history = build_portfolio_timeseries(tx, price_frame, fx)
        current = calculate_positions(tx)
        current_rows = []
        latest_date = price_frame.index.max()
        for ticker, position in current.iterrows():
            asset = asset_map[ticker]
            currency = asset.currency.upper() if asset else "EUR"
            latest_local_price = float(price_frame.loc[:latest_date, ticker].ffill().iloc[-1])
            rate = float(fx.loc[:latest_date, currency].ffill().iloc[-1])
            quantity = float(position["quantity"])
            local_value = quantity * latest_local_price
            current_rows.append(
                {
                    "ticker": ticker,
                    "name": asset.name if asset else ticker,
                    "currency": currency,
                    "quantity": quantity,
                    "average_cost": float(position["average_cost"]),
                    "price": latest_local_price,
                    "value": local_value,
                    "value_eur": local_value * rate,
                    "profit_loss": quantity
                    * (latest_local_price - float(position["average_cost"])),
                    "realized_pnl": float(position["realized_pnl"]),
                }
            )
        holdings = pd.DataFrame(current_rows).set_index("ticker")
        latest = history.iloc[-1]
        metrics = calculate_metrics(float(latest["value"]), float(latest["invested_capital"]))
        return history, holdings, metrics, warnings

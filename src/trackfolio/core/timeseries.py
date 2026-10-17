"""Historical portfolio valuation calculations."""

from collections.abc import Mapping

import numpy as np
import pandas as pd

from trackfolio.models import TransactionType


def build_portfolio_timeseries(
    transactions: pd.DataFrame,
    prices: pd.DataFrame,
    fx_rates: pd.DataFrame | None = None,
    asset_currencies: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Build daily EUR portfolio value and net invested capital series.

    Prices are in each asset's local currency. FX columns contain local-currency-to-EUR
    multipliers and must include transaction currencies as well as price currencies.
    ``asset_currencies`` maps ticker to the currency its price is quoted in; tickers not in
    the map fall back to the currency of their first transaction.
    Raises ValueError for unknown transaction types, missing prices or FX rates, and a
    non-zero holding without a price.
    """
    if transactions.empty:
        return pd.DataFrame(columns=["value", "invested_capital"], index=pd.DatetimeIndex([]))
    required = {"date", "ticker", "type", "quantity", "price", "fees", "currency"}
    missing = required.difference(transactions.columns)
    if missing:
        raise ValueError(f"Missing transaction columns: {', '.join(sorted(missing))}")

    tx = transactions.copy()
    tx["date"] = pd.to_datetime(tx["date"]).dt.normalize()
    tx["ticker"] = tx["ticker"].str.upper()
    tx["currency"] = tx["currency"].str.upper()
    tx["type"] = tx["type"].astype(str).str.upper()
    valid_types = {TransactionType.BUY.value, TransactionType.SELL.value}
    unknown_types = set(tx["type"]).difference(valid_types)
    if unknown_types:
        raise ValueError(f"Unknown transaction types: {', '.join(sorted(unknown_types))}")
    price_data = prices.copy()
    price_data.index = pd.to_datetime(price_data.index).normalize()
    price_data.columns = price_data.columns.astype(str).str.upper()
    if price_data.empty:
        raise ValueError("At least one price observation is required")
    if not set(tx["ticker"]).issubset(price_data.columns):
        missing_tickers = sorted(set(tx["ticker"]).difference(price_data.columns))
        raise ValueError(f"Missing price series for: {', '.join(missing_tickers)}")

    price_data = price_data[sorted(set(tx["ticker"]))]
    price_currencies = tx.drop_duplicates("ticker").set_index("ticker")["currency"].to_dict()
    if asset_currencies:
        price_currencies.update(
            {str(k).upper(): str(v).upper() for k, v in asset_currencies.items()}
        )
    price_currencies = {t: price_currencies[t] for t in price_data.columns}

    start = tx["date"].min()
    end = max(price_data.index.max(), tx["date"].max())
    if end.weekday() >= 5:
        end += pd.offsets.BDay(1)
    dates = pd.date_range(start, end, freq="B")
    if dates.empty:
        dates = pd.date_range(start, start + pd.offsets.BDay(1), freq="B")
    prices_aligned = (
        price_data.sort_index().reindex(price_data.index.union(dates)).ffill().reindex(dates)
    )

    currencies = set(tx["currency"]) | set(price_currencies.values())
    fx = pd.DataFrame(index=dates, columns=sorted(currencies), dtype="float64")
    if fx_rates is not None:
        rates = fx_rates.copy()
        rates.index = pd.to_datetime(rates.index).normalize()
        rates.columns = rates.columns.astype(str).str.upper()
        rates = rates.sort_index()
        fx = (
            rates.reindex(rates.index.union(dates))
            .ffill()
            .reindex(dates)
            .reindex(columns=sorted(currencies))
        )
    if "EUR" in fx.columns:
        fx["EUR"] = 1.0
    if fx.isna().any().any():
        missing_currencies = fx.columns[fx.isna().any()].tolist()
        raise ValueError(f"Missing FX rates for: {', '.join(missing_currencies)}")

    sign = np.where(tx["type"] == TransactionType.BUY.value, 1.0, -1.0)
    tx["delta"] = tx["quantity"] * sign
    tx["valuation_date"] = dates[np.minimum(dates.searchsorted(tx["date"]), len(dates) - 1)]
    quantity_matrix = (
        tx.pivot_table(
            index="valuation_date", columns="ticker", values="delta", aggfunc="sum", fill_value=0.0
        )
        .reindex(index=dates, columns=price_data.columns, fill_value=0.0)
        .cumsum()
    )

    eur_prices = prices_aligned.copy()
    for ticker in eur_prices.columns:
        currency = price_currencies[ticker]
        if currency != "EUR":
            eur_prices[ticker] = eur_prices[ticker] * fx[currency]
    unpriced = (quantity_matrix.abs() > 1e-12) & eur_prices.isna()
    if unpriced.any().any():
        bad = ", ".join(unpriced.columns[unpriced.any()])
        raise ValueError(f"Holdings without a price before first quote for: {bad}")
    values = (quantity_matrix * eur_prices).sum(axis=1)

    signed_flows = []
    for row in tx.itertuples(index=False):
        amount = row.quantity * row.price
        if row.type == TransactionType.BUY.value:
            flow = amount + row.fees
        else:
            flow = -(amount - row.fees)
        flow_date = dates[min(dates.searchsorted(row.date), len(dates) - 1)]
        rate = fx.loc[flow_date, row.currency]
        signed_flows.append((flow_date, flow * rate))
    flow_series = pd.Series(
        [amount for _, amount in signed_flows],
        index=pd.DatetimeIndex([timestamp for timestamp, _ in signed_flows]),
    )
    invested = flow_series.groupby(level=0).sum().reindex(dates, fill_value=0).cumsum()
    return pd.DataFrame({"value": values, "invested_capital": invested}, index=dates).rename_axis(
        "date"
    )

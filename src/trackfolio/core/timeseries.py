"""Historical portfolio valuation calculations."""

import pandas as pd

from trackfolio.models import TransactionType


def build_portfolio_timeseries(
    transactions: pd.DataFrame,
    prices: pd.DataFrame,
    fx_rates: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build daily EUR portfolio value and net invested capital series.

    Prices are in each asset's local currency. FX columns contain local-currency-to-EUR
    multipliers and must include transaction currencies as well as price currencies.
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
    price_data = prices.copy()
    price_data.index = pd.to_datetime(price_data.index).normalize()
    price_data.columns = price_data.columns.astype(str).str.upper()
    if price_data.empty:
        raise ValueError("At least one price observation is required")
    if not set(tx["ticker"]).issubset(price_data.columns):
        missing_tickers = sorted(set(tx["ticker"]).difference(price_data.columns))
        raise ValueError(f"Missing price series for: {', '.join(missing_tickers)}")

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

    currencies = set(tx["currency"])
    currencies.update(
        str(row.currency).upper() for row in tx.itertuples(index=False) if hasattr(row, "currency")
    )
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

    asset_currencies = tx.drop_duplicates("ticker").set_index("ticker")["currency"].to_dict()
    quantity_matrix = pd.DataFrame(0.0, index=dates, columns=price_data.columns)
    for ticker, ticker_tx in tx.groupby("ticker"):
        ticker_tx = ticker_tx.copy()
        ticker_tx["valuation_date"] = ticker_tx["date"].map(
            lambda tx_date: dates[min(dates.searchsorted(tx_date), len(dates) - 1)]
        )
        deltas = (
            ticker_tx.assign(
                delta=ticker_tx.apply(
                    lambda row: (
                        row["quantity"]
                        if row["type"] == TransactionType.BUY.value
                        else -row["quantity"]
                    ),
                    axis=1,
                )
            )
            .groupby("valuation_date")["delta"]
            .sum()
        )
        quantity_matrix[ticker] = deltas.reindex(dates, fill_value=0).cumsum()

    eur_prices = prices_aligned.copy()
    for ticker in eur_prices.columns:
        currency = asset_currencies[ticker]
        if currency != "EUR":
            eur_prices[ticker] = eur_prices[ticker] * fx[currency]
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

"""Current holdings valued from latest prices and FX rates."""

from collections.abc import Mapping

import pandas as pd


def build_holdings(
    positions: pd.DataFrame,
    prices: pd.DataFrame,
    fx: pd.DataFrame,
    asset_info: Mapping[str, tuple[str, str]],
) -> pd.DataFrame:
    """Value open positions at the latest price; ``asset_info`` maps ticker to (name, currency)."""
    rows = []
    for ticker, position in positions.iterrows():
        name, currency = asset_info.get(str(ticker), (str(ticker), "EUR"))
        price = float(prices[ticker].ffill().iloc[-1])
        rate = float(fx[currency].ffill().iloc[-1])
        quantity = float(position["quantity"])
        average_cost = float(position["average_cost"])
        value = quantity * price
        rows.append(
            {
                "ticker": ticker,
                "name": name,
                "currency": currency,
                "quantity": quantity,
                "average_cost": average_cost,
                "price": price,
                "value": value,
                "value_eur": value * rate,
                "profit_loss": quantity * (price - average_cost),
                "realized_pnl": float(position["realized_pnl"]),
            }
        )
    return pd.DataFrame(rows).set_index("ticker")

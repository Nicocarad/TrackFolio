"""Current holdings valued from latest prices and FX rates."""

from collections.abc import Mapping

import pandas as pd


def build_holdings(
    positions: pd.DataFrame,
    prices: pd.DataFrame,
    fx: pd.DataFrame,
    asset_info: Mapping[str, tuple[str, str]],
) -> pd.DataFrame:
    """Value positions at the latest price; ``asset_info`` maps ticker to (name, currency).

    EUR columns use the latest FX rate for every amount, including realized P/L and dividends
    earned earlier at different rates, so they are approximations of the historical EUR amounts.
    """
    rows = []
    for ticker, position in positions.iterrows():
        name, currency = asset_info.get(str(ticker), (str(ticker), "EUR"))
        price = float(prices[ticker].ffill().iloc[-1])
        rate = float(fx[currency].ffill().iloc[-1])
        quantity = float(position["quantity"])
        average_cost = float(position["average_cost"])
        value = quantity * price
        profit_loss = quantity * (price - average_cost)
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
                "profit_loss": profit_loss,
                "profit_loss_pct": (price / average_cost - 1) * 100 if average_cost else None,
                "profit_loss_eur": profit_loss * rate,
                "realized_pnl": float(position["realized_pnl"]),
                "realized_pnl_eur": float(position["realized_pnl"]) * rate,
                "dividends": float(position["dividends"]),
                "dividends_eur": float(position["dividends"]) * rate,
            }
        )
    return pd.DataFrame(rows).set_index("ticker")

"""Time-weighted and money-weighted returns from a value/invested-capital series."""

import pandas as pd

_DAYS_PER_YEAR = 365.0


def daily_twr_returns(history: pd.DataFrame) -> pd.Series:
    """Daily time-weighted returns; cash flows are assumed to occur at the end of the day.

    ``history`` needs ``value`` and ``invested_capital`` columns (cumulative net flows).
    Days following a zero or negative value have no defined return and are left out.
    """
    flow = history["invested_capital"].diff().fillna(history["invested_capital"])
    previous = history["value"].shift(1)
    returns = (history["value"] - flow) / previous - 1
    return returns[previous > 0].dropna()


def twr_pct(history: pd.DataFrame, since: pd.Timestamp | None = None) -> float | None:
    """Chain-linked time-weighted return in percent, optionally from the day after ``since``."""
    returns = daily_twr_returns(history)
    if since is not None:
        returns = returns[returns.index > since]
    if returns.empty:
        return None
    return float((1 + returns).prod() - 1) * 100


def period_returns_pct(history: pd.DataFrame) -> dict[str, float | None]:
    """YTD, 1Y and 3Y time-weighted returns ending at the last date of ``history``."""
    if history.empty:
        return {"YTD": None, "1Y": None, "3Y": None}
    end = history.index.max()
    starts = {
        "YTD": pd.Timestamp(year=end.year - 1, month=12, day=31),
        "1Y": end - pd.DateOffset(years=1),
        "3Y": end - pd.DateOffset(years=3),
    }
    return {
        label: twr_pct(history, start) if history.index.min() <= start else None
        for label, start in starts.items()
    }


def xirr_pct(history: pd.DataFrame) -> float | None:
    """Annualized money-weighted return in percent, or None when it is undefined.

    Investments are outflows, withdrawals inflows, and the final value is a closing inflow.
    """
    if history.empty:
        return None
    invested = history["invested_capital"]
    flows = invested.diff().fillna(invested)
    flows = flows[flows != 0]
    end = history.index.max()
    amounts = [-float(amount) for amount in flows] + [float(history["value"].iloc[-1])]
    years = [(date - history.index.min()).days / _DAYS_PER_YEAR for date in [*flows.index, end]]
    if not flows.size or min(amounts) >= 0 or max(amounts) <= 0:
        return None

    def npv(rate: float) -> float:
        return float(sum(a / (1 + rate) ** y for a, y in zip(amounts, years, strict=True)))

    low, high = -0.999, 100.0
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        if npv(low) * npv(mid) <= 0:
            high = mid
        else:
            low = mid
    return (low + high) / 2 * 100

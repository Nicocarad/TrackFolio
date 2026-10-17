"""Portfolio summary metrics."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioMetrics:
    """Top-level portfolio KPIs in the base currency."""

    total_value: float
    invested_capital: float
    profit_loss: float
    return_pct: float
    twr_pct: float | None = None
    xirr_pct: float | None = None


def calculate_metrics(
    total_value: float,
    invested_capital: float,
    twr_pct: float | None = None,
    xirr_pct: float | None = None,
) -> PortfolioMetrics:
    """Calculate absolute and percentage return.

    ``return_pct`` is relative to net invested capital and is not meaningful once that is
    close to zero or negative (after a profitable exit); prefer ``twr_pct`` and ``xirr_pct``.
    """
    profit_loss = total_value - invested_capital
    return_pct = profit_loss / invested_capital * 100 if invested_capital else 0.0
    return PortfolioMetrics(
        total_value, invested_capital, profit_loss, return_pct, twr_pct, xirr_pct
    )

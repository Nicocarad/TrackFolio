"""Portfolio summary metrics."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioMetrics:
    """Top-level portfolio KPIs in the base currency."""

    total_value: float
    invested_capital: float
    profit_loss: float
    return_pct: float


def calculate_metrics(total_value: float, invested_capital: float) -> PortfolioMetrics:
    """Calculate absolute and percentage return."""
    profit_loss = total_value - invested_capital
    return_pct = profit_loss / invested_capital * 100 if invested_capital else 0.0
    return PortfolioMetrics(total_value, invested_capital, profit_loss, return_pct)

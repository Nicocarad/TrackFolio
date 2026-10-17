from trackfolio.core.metrics import calculate_metrics


def test_metrics_calculate_absolute_and_percentage_return() -> None:
    metrics = calculate_metrics(125, 100)
    assert metrics.profit_loss == 25
    assert metrics.return_pct == 25


def test_metrics_with_zero_invested_capital() -> None:
    metrics = calculate_metrics(10, 0)
    assert metrics.profit_loss == 10
    assert metrics.return_pct == 0


def test_metrics_loss_gives_negative_return() -> None:
    metrics = calculate_metrics(80, 100)
    assert metrics.profit_loss == -20
    assert metrics.return_pct == -20


def test_metrics_negative_invested_capital_keeps_profit_loss() -> None:
    # return_pct is not meaningful here (backlog A6); only the absolute P/L is asserted.
    metrics = calculate_metrics(50, -30)
    assert metrics.profit_loss == 80


def test_period_returns_are_carried_on_the_metrics() -> None:
    metrics = calculate_metrics(110, 100, period_returns={"YTD": 10.0, "1Y": None})
    assert metrics.period_returns == {"YTD": 10.0, "1Y": None}
    assert calculate_metrics(0, 0).period_returns == {}

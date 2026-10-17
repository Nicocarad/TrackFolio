from trackfolio.core.metrics import calculate_metrics


def test_metrics_calculate_absolute_and_percentage_return() -> None:
    metrics = calculate_metrics(125, 100)
    assert metrics.profit_loss == 25
    assert metrics.return_pct == 25


def test_metrics_with_zero_invested_capital() -> None:
    metrics = calculate_metrics(10, 0)
    assert metrics.profit_loss == 10
    assert metrics.return_pct == 0

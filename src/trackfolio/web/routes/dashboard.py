"""Dashboard page and price refresh."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from trackfolio.services.portfolio_service import PortfolioService
from trackfolio.web.deps import get_service, require_csrf
from trackfolio.web.routes.templating import templates

router = APIRouter(dependencies=[Depends(require_csrf)])


def _context(service: PortfolioService, notice: str | None = None) -> dict[str, Any]:
    history, holdings, metrics, warnings = service.dashboard_data()
    value_chart: dict[str, Any] | None = None
    allocation_chart: dict[str, Any] | None = None
    if not history.empty:
        value_chart = {
            "dates": [d.strftime("%Y-%m-%d") for d in history.index],
            "value": history["value"].round(2).tolist(),
            "invested": history["invested_capital"].round(2).tolist(),
        }
        open_positions = holdings[holdings["value_eur"] > 0]
        if not open_positions.empty:
            allocation_chart = {
                "labels": open_positions.index.tolist(),
                "values": open_positions["value_eur"].round(2).tolist(),
            }
    rows = holdings.reset_index().to_dict("records") if not holdings.empty else []
    totals = (
        {
            "unrealized": float(holdings["profit_loss_eur"].sum()),
            "realized": float(holdings["realized_pnl_eur"].sum()),
            "dividends": float(holdings["dividends_eur"].sum()),
        }
        if not holdings.empty
        else None
    )
    return {
        "metrics": metrics,
        "warnings": warnings,
        "empty": history.empty,
        "value_chart": value_chart,
        "allocation_chart": allocation_chart,
        "holdings": rows,
        "totals": totals,
        "notice": notice,
        "last_price_date": service.last_price_date(),
    }


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, service: PortfolioService = Depends(get_service)) -> Any:
    """Render the dashboard."""
    return templates.TemplateResponse(
        request, "dashboard.html", {"page": "dashboard", **_context(service)}
    )


@router.post("/refresh", response_class=HTMLResponse)
def refresh(request: Request, service: PortfolioService = Depends(get_service)) -> Any:
    """Refresh cached prices and re-render the dashboard body."""
    count, errors = service.refresh_prices()
    notice = None if errors else f"Aggiornati {count} prezzi giornalieri."
    context = _context(service, notice)
    context["warnings"] = [*errors, *context["warnings"]]
    return templates.TemplateResponse(request, "_dashboard.html", context)

"""Transaction list, entry, editing, deletion and instrument search."""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from trackfolio.models import Transaction, TransactionType
from trackfolio.services.portfolio_service import PortfolioService
from trackfolio.web.deps import get_service
from trackfolio.web.messages import error_text
from trackfolio.web.routes.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter()

TYPE_LABELS = {
    TransactionType.BUY: "BUY",
    TransactionType.SELL: "SELL",
    TransactionType.SPLIT: "SPLIT (rapporto)",
    TransactionType.DIVIDEND: "DIVIDEND",
}


def _context(
    service: PortfolioService,
    *,
    current: Transaction | None = None,
    prefill: dict[str, str] | None = None,
    message: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    existing = service.list_transactions()
    currencies = service.asset_currencies()
    values = prefill or {}
    ticker = current.ticker if current else values.get("ticker", "")
    return {
        "transactions": existing,
        "currencies": currencies,
        "current": current,
        "types": TYPE_LABELS,
        "ticker": ticker,
        "isin": values.get("isin", ""),
        "currency": currencies.get(ticker) or values.get("currency", ""),
        "today": date.today().isoformat(),
        "message": message,
        "error": error,
    }


def _area(request: Request, service: PortfolioService, **kwargs: Any) -> Any:
    return templates.TemplateResponse(
        request, "_transactions_area.html", _context(service, **kwargs)
    )


@router.get("/transactions", response_class=HTMLResponse)
def transactions_page(request: Request, service: PortfolioService = Depends(get_service)) -> Any:
    """Render the transactions page."""
    return templates.TemplateResponse(
        request, "transactions.html", {"page": "transactions", **_context(service)}
    )


@router.get("/transactions/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", service: PortfolioService = Depends(get_service)) -> Any:
    """Return the candidate listings for an ISIN, ticker or name."""
    candidates, error = [], None
    if q.strip():
        try:
            candidates = service.search_instrument(q)
            error = None if candidates else "Nessun titolo trovato."
        except (ValueError, RuntimeError) as exc:
            error = error_text(exc)
    return templates.TemplateResponse(
        request, "_candidates.html", {"candidates": candidates, "error": error}
    )


@router.get("/transactions/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    ticker: str = "",
    isin: str = "",
    currency: str = "",
    service: PortfolioService = Depends(get_service),
) -> Any:
    """Return the area with the form prefilled from a chosen listing."""
    return _area(request, service, prefill={"ticker": ticker, "isin": isin, "currency": currency})


@router.get("/transactions/{transaction_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request, transaction_id: int, service: PortfolioService = Depends(get_service)
) -> Any:
    """Return the area with the form loaded with an existing transaction."""
    current = next((t for t in service.list_transactions() if t.id == transaction_id), None)
    if current is None:
        return _area(request, service, error=f"La transazione {transaction_id} non esiste.")
    return _area(request, service, current=current)


@router.post("/transactions", response_class=HTMLResponse)
def save(
    request: Request,
    tx_date: date = Form(alias="date"),
    ticker: str = Form(),
    type: TransactionType = Form(),
    quantity: float = Form(),
    price: str = Form("0"),
    fees: str = Form("0"),
    notes: str = Form(""),
    transaction_id: str = Form("", alias="id"),
    isin: str = Form(""),
    service: PortfolioService = Depends(get_service),
) -> Any:
    """Insert or update a transaction and return the refreshed area."""
    prefill = {"ticker": ticker.strip().upper(), "isin": isin}
    try:
        transaction = Transaction(
            id=int(transaction_id) if transaction_id.strip() else None,
            user_id=service.user_id,
            date=tx_date,
            ticker=ticker.strip().upper(),
            type=type,
            quantity=quantity,
            price=float(price or 0),
            fees=float(fees or 0),
            notes=notes.strip() or None,
        )
    except ValueError:
        return _area(request, service, prefill=prefill, error="Valori numerici non validi.")
    try:
        service.save_transaction(transaction, isin or None)
    except (ValueError, RuntimeError) as exc:
        return _area(request, service, current=transaction, prefill=prefill, error=error_text(exc))
    except Exception:
        logger.exception("Unexpected error while saving a transaction")
        return _area(
            request, service, current=transaction, prefill=prefill, error="Errore imprevisto."
        )
    return _area(request, service, message="Transazione salvata.")


@router.post("/transactions/{transaction_id}/delete", response_class=HTMLResponse)
def delete(
    request: Request, transaction_id: int, service: PortfolioService = Depends(get_service)
) -> Any:
    """Delete a transaction and return the refreshed area."""
    try:
        service.delete_transaction(transaction_id)
    except ValueError as exc:
        return _area(request, service, error=error_text(exc))
    return _area(request, service, message="Transazione eliminata.")

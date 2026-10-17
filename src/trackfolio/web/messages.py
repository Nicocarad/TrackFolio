"""Italian texts for the structured warnings returned by the service."""

from typing import assert_never

from trackfolio.services.portfolio_service import DataWarning, WarningCode


def warning_text(warning: DataWarning) -> str:
    """Render a service warning for the page."""
    match warning.code:
        case WarningCode.NO_PRICE:
            return f"Nessun prezzo in cache per {warning.subject}"
        case WarningCode.NO_FX:
            return f"Nessun tasso di cambio in cache per {warning.subject}/EUR"
        case WarningCode.EXCLUDED:
            return f"Esclusi dal dashboard: {warning.subject}"
        case WarningCode.REFRESH_FAILED:
            if warning.cached_until is None:
                return (
                    f"{warning.subject}: aggiornamento fallito e cache assente ({warning.detail})"
                )
            return (
                f"{warning.subject}: aggiornamento fallito; uso cache fino al "
                f"{warning.cached_until} ({warning.detail})"
            )
        case WarningCode.DATA_ERROR:
            return warning.detail
        case _ as unreachable:
            assert_never(unreachable)

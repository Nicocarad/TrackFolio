"""Italian texts for the structured warnings and domain errors returned by the service."""

from typing import assert_never

from trackfolio.errors import DomainError, ErrorCode
from trackfolio.services.warnings import DataWarning, WarningCode

ERRORS_IT: dict[ErrorCode, str] = {
    ErrorCode.INVALID_VALUES: "La transazione contiene valori mancanti o non validi.",
    ErrorCode.FUTURE_DATE: "La data non può essere nel futuro.",
    ErrorCode.TICKER_REQUIRED: "Il ticker è obbligatorio.",
    ErrorCode.INVALID_TYPE: "Tipo di transazione non valido (ammessi: {allowed}).",
    ErrorCode.QUANTITY_NOT_POSITIVE: "La quantità deve essere maggiore di zero.",
    ErrorCode.NEGATIVE_AMOUNT: "Prezzo e commissioni non possono essere negativi.",
    ErrorCode.SPLIT_HAS_PRICE: "Uno split non ha prezzo né commissioni: la quantità è il rapporto.",
    ErrorCode.OVERSELL: (
        "Impossibile vendere {quantity:g} di {ticker} il {date}: "
        "le quote in portafoglio diventerebbero negative ({holdings:g})."
    ),
    ErrorCode.SELL_EXCEEDS: "La vendita di {ticker} il {date} supera le quote detenute.",
    ErrorCode.DIVIDEND_EXCEEDS: (
        "Il dividendo su {quantity:g} titoli {ticker} il {date} supera le quote "
        "detenute ({holdings:g})."
    ),
    ErrorCode.TRANSACTION_NOT_FOUND: "La transazione {transaction_id} non esiste.",
    ErrorCode.MISSING_COLUMNS: "Colonne mancanti nelle transazioni: {columns}.",
    ErrorCode.UNKNOWN_TYPE: "Tipo di transazione sconosciuto: {types}.",
    ErrorCode.NO_PRICES: "Serve almeno un prezzo.",
    ErrorCode.MISSING_PRICE_SERIES: "Prezzi mancanti per: {tickers}.",
    ErrorCode.MISSING_CURRENCY: "Valuta mancante per: {tickers}.",
    ErrorCode.MISSING_FX: "Tassi di cambio mancanti per: {currencies}.",
    ErrorCode.UNPRICED_HOLDINGS: "Posizioni senza prezzo prima della prima quotazione: {tickers}.",
    ErrorCode.INVALID_ISIN: "ISIN non valido (formato o cifra di controllo).",
    ErrorCode.EMPTY_QUERY: "Inserisci un ISIN, un ticker o un nome.",
    ErrorCode.UNKNOWN_TICKER: "Yahoo Finance non riconosce il ticker {ticker}.",
    ErrorCode.NO_HISTORY: "Nessuna storia dei prezzi disponibile per {ticker}.",
    ErrorCode.EMAIL_INVALID: "Indirizzo email non valido.",
    ErrorCode.EMAIL_TAKEN: "Esiste già un utente con email {email}.",
    ErrorCode.PASSWORD_TOO_SHORT: "La password deve avere almeno {minimum} caratteri.",
    ErrorCode.USER_NOT_FOUND: "Nessun utente con email {email}.",
    ErrorCode.RATE_LIMITED: "Troppi tentativi. Riprova tra {seconds} secondi.",
}


def error_text(error: Exception) -> str:
    """Italian text for a domain error; other errors (providers) keep their own message."""
    if isinstance(error, DomainError):
        return ERRORS_IT[error.code].format(**error.params)
    return str(error)


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
            return error_text(warning.error) if warning.error else warning.detail
        case _ as unreachable:
            assert_never(unreachable)

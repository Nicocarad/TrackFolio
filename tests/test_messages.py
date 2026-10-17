from datetime import date

from trackfolio.services.portfolio_service import DataWarning, WarningCode
from trackfolio.web.messages import warning_text


def test_every_warning_code_has_an_italian_text() -> None:
    cached = date(2025, 1, 3)
    cases = {
        DataWarning(WarningCode.NO_PRICE, "ABC"): "Nessun prezzo in cache per ABC",
        DataWarning(WarningCode.NO_FX, "USD"): "Nessun tasso di cambio in cache per USD/EUR",
        DataWarning(WarningCode.EXCLUDED, "A, B"): "Esclusi dal dashboard: A, B",
        DataWarning(WarningCode.REFRESH_FAILED, "ABC", "down"): (
            "ABC: aggiornamento fallito e cache assente (down)"
        ),
        DataWarning(WarningCode.REFRESH_FAILED, "ABC", "down", cached): (
            "ABC: aggiornamento fallito; uso cache fino al 2025-01-03 (down)"
        ),
        DataWarning(WarningCode.DATA_ERROR, detail="Missing FX rates for: USD"): (
            "Missing FX rates for: USD"
        ),
    }
    for warning, text in cases.items():
        assert warning_text(warning) == text
    assert {w.code for w in cases} == set(WarningCode)


def test_every_error_code_has_an_italian_text_and_formats() -> None:
    from trackfolio.errors import MESSAGES, DomainError, ErrorCode
    from trackfolio.web.messages import ERRORS_IT, error_text

    assert set(ERRORS_IT) == set(ErrorCode) == set(MESSAGES)
    params = {
        "allowed": "BUY",
        "quantity": 5.0,
        "ticker": "ABC",
        "date": "2025-01-03",
        "holdings": 3.0,
        "transaction_id": 9,
        "columns": "a",
        "types": "X",
        "tickers": "ABC",
        "currencies": "USD",
        "email": "a@example.com",
        "minimum": 12,
    }
    for code in ErrorCode:
        error = DomainError(code, **params)
        assert str(error)  # English text formats too
        assert error_text(error) == ERRORS_IT[code].format(**params)
    assert error_text(RuntimeError("down")) == "down"


def test_oversell_is_reported_in_italian_in_the_form() -> None:
    from trackfolio.errors import DomainError, ErrorCode
    from trackfolio.web.messages import error_text

    error = DomainError(
        ErrorCode.OVERSELL, quantity=5.0, ticker="ABC", date="2025-01-03", holdings=-3.0
    )
    assert error_text(error) == (
        "Impossibile vendere 5 di ABC il 2025-01-03: le quote in portafoglio "
        "diventerebbero negative (-3)."
    )

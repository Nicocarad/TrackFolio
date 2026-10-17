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

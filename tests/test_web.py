from collections.abc import Generator
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from trackfolio.models import Asset, User
from trackfolio.web.app import create_app
from trackfolio.web.deps import get_db, get_provider


class FakeProvider:
    def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
        dates = pd.bdate_range(start=start, end=end - timedelta(days=1))
        return pd.Series([10.0 + i for i in range(len(dates))], index=dates, name=ticker)

    def get_asset(self, ticker: str) -> Asset:
        return Asset(ticker=ticker, name=f"{ticker} Inc", currency="EUR")

    def search_tickers(self, query: str) -> list[Asset]:
        if query.upper() == "NONE":
            return []
        return [self.get_asset(query.upper())]


@pytest.fixture
def client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(User(email="a@example.com", password_hash="x"))
        session.commit()

    def override_db() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app = create_app(migrate=False)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as test_client:
        yield test_client


def _form(**overrides: str) -> dict[str, str]:
    day = (date.today() - timedelta(days=5)).isoformat()
    return {
        "date": day,
        "ticker": "abc",
        "type": "BUY",
        "quantity": "2",
        "price": "10",
        "fees": "1",
        **overrides,
    }


def test_empty_dashboard_and_static_assets(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "Aggiungi una" in page.text
    assert client.get("/static/htmx.min.js").status_code == 200
    plotly = client.get("/static/plotly.min.js")
    assert plotly.status_code == 200 and "javascript" in plotly.headers["content-type"]


def test_add_transaction_then_refresh_shows_dashboard(client: TestClient) -> None:
    saved = client.post("/transactions", data=_form())
    assert "Transazione salvata." in saved.text
    assert "ABC" in saved.text

    refreshed = client.post("/refresh")
    assert "Aggiornati" in refreshed.text
    dashboard = client.get("/")
    assert "Valore totale" in dashboard.text
    assert "€ 21.00" in dashboard.text.replace("\xa0", " ")  # invested: 2 * 10 + 1 fees


def test_invalid_transaction_returns_the_form_with_an_error(client: TestClient) -> None:
    response = client.post("/transactions", data=_form(type="SELL", quantity="5"))
    assert response.status_code == 200
    assert "diventerebbero negative" in response.text
    assert client.get("/transactions").text.count("<td>ABC</td>") == 0


def test_edit_and_delete(client: TestClient) -> None:
    client.post("/transactions", data=_form())
    edit = client.get("/transactions/1/edit")
    assert "Modifica transazione" in edit.text
    updated = client.post("/transactions", data=_form(id="1", quantity="3"))
    assert "Transazione salvata." in updated.text
    assert ">3<" in updated.text.replace(" ", "") or "3.000000" in updated.text
    deleted = client.post("/transactions/1/delete")
    assert "Transazione eliminata." in deleted.text
    assert "Nessuna transazione." in deleted.text
    missing = client.post("/transactions/99/delete")
    assert "non esiste" in missing.text


def test_search_detects_isin_and_reports_empty_results(client: TestClient) -> None:
    found = client.get("/transactions/search", params={"q": "abc"})
    assert "ABC Inc" in found.text and "hx-get" in found.text
    none = client.get("/transactions/search", params={"q": "none"})
    assert "Nessun titolo trovato." in none.text
    bad_isin = client.get("/transactions/search", params={"q": "IE00BK5BQT80"})
    assert bad_isin.status_code == 200


def test_new_form_is_prefilled_from_a_listing(client: TestClient) -> None:
    form = client.get(
        "/transactions/new", params={"ticker": "VWCE.DE", "isin": "IE00BK5BQT80", "currency": "EUR"}
    )
    assert 'value="VWCE.DE"' in form.text
    assert 'value="IE00BK5BQT80"' in form.text


def test_empty_price_and_fees_are_treated_as_zero_and_bad_numbers_are_reported(
    client: TestClient,
) -> None:
    ok = client.post("/transactions", data=_form(price="", fees=""))
    assert "Transazione salvata." in ok.text
    bad = client.post("/transactions", data=_form(price="abc"))
    assert "Valori numerici non validi." in bad.text
    tampered = client.post("/transactions", data=_form(id="x"))
    assert "Valori numerici non validi." in tampered.text


def test_failed_save_keeps_the_isin_in_the_form(client: TestClient) -> None:
    response = client.post(
        "/transactions", data=_form(type="SELL", quantity="5", isin="IE00BK5BQT80")
    )
    assert "diventerebbero negative" in response.text
    assert 'name="isin" value="IE00BK5BQT80"' in response.text


def test_dashboard_shows_realized_dividends_and_per_position_columns(client: TestClient) -> None:
    client.post("/transactions", data=_form(quantity="10", price="10", fees="0"))
    client.post(
        "/transactions",
        data=_form(
            type="DIVIDEND", quantity="10", price="0.5", fees="1", date=date.today().isoformat()
        ),
    )
    client.post("/refresh")
    page = client.get("/").text
    for label in (
        "P/L non realizzato (EUR)",
        "P/L realizzato (EUR)",
        "Dividendi netti (EUR)",
        "P/L %",
    ):
        assert label in page
    assert "€ 4.00" in page.replace("\xa0", " ")  # net dividend: 10 * 0.5 - 1


def test_refresh_failure_is_reported_in_italian(client: TestClient) -> None:
    class Broken(FakeProvider):
        def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
            raise RuntimeError("down")

    client.post("/transactions", data=_form())
    client.app.dependency_overrides[get_provider] = lambda: Broken()  # type: ignore[attr-defined]
    page = client.post("/refresh").text
    assert "ABC: aggiornamento fallito e cache assente (down)" in page

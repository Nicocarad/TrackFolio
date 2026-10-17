import re
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from helpers import PASSWORD, memory_engine, open_client, refresh
from sqlalchemy import Engine
from sqlmodel import Session, select

from trackfolio.errors import DomainError, ErrorCode
from trackfolio.models import UserSession
from trackfolio.services.auth_service import AuthService
from trackfolio.web.deps import COOKIE_NAME


@pytest.fixture
def engine() -> Engine:
    return memory_engine()


@pytest.fixture
def anonymous(engine: Engine) -> Generator[TestClient]:
    yield from open_client(engine)


@pytest.fixture
def alice(engine: Engine) -> Generator[TestClient]:
    yield from open_client(engine, "alice@example.com")


@pytest.fixture
def bob(engine: Engine) -> Generator[TestClient]:
    yield from open_client(engine, "bob@example.com")


def _buy(ticker: str = "ABC") -> dict[str, str]:
    return {"date": "2025-01-06", "ticker": ticker, "type": "BUY", "quantity": "2", "price": "10"}


def test_anonymous_requests_are_redirected_to_the_login_page(anonymous: TestClient) -> None:
    page = anonymous.get("/", follow_redirects=False)
    assert (page.status_code, page.headers["location"]) == (303, "/login")
    htmx = anonymous.get("/", headers={"HX-Request": "true"}, follow_redirects=False)
    assert (htmx.status_code, htmx.headers["HX-Redirect"]) == (401, "/login")
    assert anonymous.post("/transactions", follow_redirects=False).status_code == 303
    assert anonymous.get("/login").status_code == 200
    assert anonymous.get("/static/style.css").status_code == 200


def test_login_with_wrong_credentials_gives_one_generic_error(
    anonymous: TestClient, engine: Engine
) -> None:
    with Session(engine) as session:
        AuthService(session).create_user("alice@example.com", PASSWORD)
    wrong_password = anonymous.post(
        "/login", data={"email": "alice@example.com", "password": "nope-nope-nope"}
    )
    unknown_email = anonymous.post("/login", data={"email": "x@example.com", "password": PASSWORD})
    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert "Email o password non corrette." in response.text
    assert COOKIE_NAME not in anonymous.cookies


def test_login_sets_a_http_only_cookie_and_logout_ends_the_session(
    anonymous: TestClient, engine: Engine
) -> None:
    with Session(engine) as session:
        AuthService(session).create_user("alice@example.com", PASSWORD)
    response = anonymous.post(
        "/login", data={"email": "ALICE@example.com ", "password": PASSWORD}, follow_redirects=False
    )
    cookie = response.headers["set-cookie"]
    assert response.status_code == 303 and "HttpOnly" in cookie and "SameSite=lax" in cookie
    page = anonymous.get("/")
    assert page.status_code == 200 and "alice@example.com" in page.text
    token = re.search(r'X-CSRF-Token": "([^"]+)"', page.text)
    assert token

    out = anonymous.post("/logout", headers={"X-CSRF-Token": token.group(1)})
    assert (out.status_code, out.headers["HX-Redirect"]) == (204, "/login")
    assert anonymous.get("/", follow_redirects=False).status_code == 303
    with Session(engine) as session:
        assert session.exec(select(UserSession)).all() == []


def test_unsafe_requests_need_the_csrf_token_and_a_same_site_origin(alice: TestClient) -> None:
    good = alice.headers["X-CSRF-Token"]
    del alice.headers["X-CSRF-Token"]
    assert alice.post("/transactions", data=_buy()).status_code == 403
    assert (
        alice.post("/transactions", data=_buy(), headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    cross = alice.post(
        "/transactions", data=_buy(), headers={"X-CSRF-Token": good, "Origin": "https://evil.test"}
    )
    assert cross.status_code == 403
    site = alice.post(
        "/transactions",
        data=_buy(),
        headers={"X-CSRF-Token": good, "Sec-Fetch-Site": "cross-site"},
    )
    assert site.status_code == 403
    ok = alice.post("/transactions", data=_buy(), headers={"X-CSRF-Token": good})
    assert "Transazione salvata." in ok.text


def test_expired_sessions_are_rejected_and_removed(alice: TestClient, engine: Engine) -> None:
    with Session(engine) as session:
        row = session.exec(select(UserSession)).one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.add(row)
        session.commit()
    assert alice.get("/", follow_redirects=False).status_code == 303
    with Session(engine) as session:
        assert session.exec(select(UserSession)).all() == []


def test_password_reset_ends_existing_sessions(alice: TestClient, engine: Engine) -> None:
    assert alice.get("/", follow_redirects=False).status_code == 200
    with Session(engine) as session:
        AuthService(session).set_password("alice@example.com", "another long password")
    assert alice.get("/", follow_redirects=False).status_code == 303


def test_users_are_isolated_in_every_route(
    alice: TestClient, bob: TestClient, engine: Engine
) -> None:
    alice.post("/transactions", data=_buy("ABC"))
    bob.post("/transactions", data=_buy("XYZ"))

    alice_page = alice.get("/transactions").text
    bob_page = bob.get("/transactions").text
    assert "<td>ABC</td>" in alice_page and "<td>XYZ</td>" not in alice_page
    assert "<td>XYZ</td>" in bob_page and "<td>ABC</td>" not in bob_page

    # Each user owns transaction id 1 and 2; neither can read, edit or delete the other's row.
    assert "non esiste" in bob.get("/transactions/1/edit").text
    assert "non esiste" in bob.post("/transactions/1/delete").text
    hijack = bob.post("/transactions", data={**_buy("ABC"), "id": "1", "quantity": "99"})
    assert "non esiste" in hijack.text
    assert "99" not in alice.get("/transactions").text
    assert "<td>ABC</td>" in alice.get("/transactions").text

    refresh(engine)
    assert "ABC" in alice.get("/").text and "XYZ" not in alice.get("/").text


def test_account_management_validation(engine: Engine) -> None:
    with Session(engine) as session:
        auth = AuthService(session)
        auth.create_user("Alice@Example.com", PASSWORD, is_admin=True)
        with pytest.raises(DomainError) as taken:
            auth.create_user("alice@example.com", PASSWORD)
        assert taken.value.code == ErrorCode.EMAIL_TAKEN
        with pytest.raises(DomainError) as short:
            auth.create_user("b@example.com", "short")
        assert short.value.code == ErrorCode.PASSWORD_TOO_SHORT
        with pytest.raises(DomainError) as bad:
            auth.create_user("not-an-email", PASSWORD)
        assert bad.value.code == ErrorCode.EMAIL_INVALID
        with pytest.raises(DomainError) as missing:
            auth.set_password("ghost@example.com", PASSWORD)
        assert missing.value.code == ErrorCode.USER_NOT_FOUND
        auth.change_email("alice@example.com", "alice2@example.com")
        assert auth.login("alice2@example.com", PASSWORD) is not None
        assert auth.login("alice@example.com", PASSWORD) is None


def test_placeholder_account_cannot_log_in(engine: Engine) -> None:
    from trackfolio.models import User

    with Session(engine) as session:
        session.add(User(email="admin@trackfolio.local", password_hash="!", is_admin=True))
        session.commit()
        assert AuthService(session).login("admin@trackfolio.local", "!") is None
        assert AuthService(session).login("admin@trackfolio.local", "") is None


def test_docs_and_openapi_are_not_exposed(alice: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert alice.get(path, follow_redirects=False).status_code in {303, 404}


def test_cookie_is_secure_by_default(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRACKFOLIO_SECURE_COOKIES")
    client = next(open_client(engine))
    with Session(engine) as session:
        AuthService(session).create_user("s@example.com", PASSWORD)
    response = client.post(
        "/login", data={"email": "s@example.com", "password": PASSWORD}, follow_redirects=False
    )
    assert "Secure" in response.headers["set-cookie"]


def test_relogin_drops_the_previous_session(alice: TestClient, engine: Engine) -> None:
    with Session(engine) as session:
        assert len(session.exec(select(UserSession)).all()) == 1
    alice.post("/login", data={"email": "alice@example.com", "password": PASSWORD})
    with Session(engine) as session:
        assert len(session.exec(select(UserSession)).all()) == 1

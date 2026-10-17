from pathlib import Path

import pytest

from trackfolio import cli
from trackfolio.db import get_engine

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACKFOLIO_DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    get_engine.cache_clear()
    yield
    get_engine.cache_clear()


def test_create_list_reset_and_rename(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["create-user", "me@example.com", "--admin"], prompt=lambda: PASSWORD) == 0
    assert cli.main(["list-users"]) == 0
    assert "me@example.com\tadmin" in capsys.readouterr().out
    assert cli.main(["set-password", "me@example.com"], prompt=lambda: "a new long password") == 0
    assert cli.main(["change-email", "me@example.com", "you@example.com"]) == 0
    assert cli.main(["list-users"]) == 0
    assert "you@example.com" in capsys.readouterr().out


def test_errors_are_reported_with_a_nonzero_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["create-user", "me@example.com"], prompt=lambda: "short") == 1
    assert "at least 12 characters" in capsys.readouterr().err
    assert cli.main(["set-password", "ghost@example.com"], prompt=lambda: PASSWORD) == 1
    assert "No user with email" in capsys.readouterr().err


def _seed_transaction(ticker: str = "ABC") -> None:
    from datetime import date, timedelta

    from trackfolio.db import get_session, init_db
    from trackfolio.models import Asset, Transaction, TransactionType, User
    from trackfolio.repositories import assets, transactions

    init_db()
    with get_session() as session:
        user = User(email="me@example.com", password_hash="x")
        session.add(user)
        session.commit()
        assert user.id is not None
        assets.save_asset(session, Asset(ticker=ticker, name=ticker, currency="EUR"))
        transactions.save_transaction(
            session,
            user.id,
            Transaction(
                user_id=user.id,
                date=date.today() - timedelta(days=5),
                ticker=ticker,
                type=TransactionType.BUY,
                quantity=1,
                price=10,
            ),
        )
        session.commit()


def test_refresh_prices_fetches_every_held_ticker(capsys: pytest.CaptureFixture[str]) -> None:
    from helpers import FakeProvider

    from trackfolio.db import get_session
    from trackfolio.repositories import prices

    _seed_transaction()
    assert cli.main(["refresh-prices"], provider=FakeProvider()) == 0
    assert "Saved" in capsys.readouterr().out
    with get_session() as session:
        assert not prices.get_prices(session, "ABC").empty


def test_refresh_prices_exits_nonzero_only_when_nothing_was_refreshed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from datetime import date

    import pandas as pd
    from helpers import FakeProvider

    class Down(FakeProvider):
        def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
            raise RuntimeError("yahoo down")

    _seed_transaction()
    assert cli.main(["refresh-prices"], provider=Down()) == 1
    assert "WARNING ABC: yahoo down" in capsys.readouterr().err

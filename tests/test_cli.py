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

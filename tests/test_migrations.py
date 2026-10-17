from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, create_engine

from trackfolio.db import _alembic_config, configure_engine, init_db

INSERT = (
    'INSERT INTO "transaction" (date, ticker, type, quantity, price, fees) '
    "VALUES ('2024-01-02', 'ABC', 'BUY', {quantity}, 1, 0)"
)
INSERT_V1 = (
    'INSERT INTO "transaction" (date, ticker, type, quantity, price, fees, currency) '
    "VALUES ('2024-01-02', 'ABC', 'BUY', {quantity}, 1, 0, '{currency}')"
)


def _engine(path: Path) -> Engine:
    return configure_engine(create_engine(f"sqlite:///{path}"))


def _version(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar())


def test_fresh_database_matches_models_and_enforces_checks(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "fresh.db")
    init_db(engine)

    assert _version(engine) == "0003"
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), SQLModel.metadata)
    assert diff == []
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO asset (ticker, name, currency) VALUES ('ABC','A','EUR')")
        )
        with pytest.raises(IntegrityError):
            connection.execute(text(INSERT.format(quantity=-1)))


def test_legacy_database_is_backed_up_stamped_and_keeps_data(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    engine = _engine(path)
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
        connection.execute(text("DROP TABLE alembic_version"))
        connection.execute(
            text("INSERT INTO asset (ticker, name, currency) VALUES ('ABC','A','EUR')")
        )
        connection.execute(text(INSERT_V1.format(quantity=-1, currency="EUR")))  # no CHECKs yet

    with pytest.raises(IntegrityError):
        init_db(engine)  # the bad legacy row blocks the CHECK migration

    assert list(tmp_path.glob("legacy.db.pre-migration-*"))
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM "transaction"'))
        connection.execute(text(INSERT_V1.format(quantity=3, currency="EUR")))
    init_db(engine)

    assert _version(engine) == "0003"
    with engine.connect() as connection:
        assert connection.execute(text('SELECT quantity FROM "transaction"')).scalar() == 3


def test_currency_column_migration_refuses_mismatched_rows(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "mismatch.db")
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002")
        connection.execute(
            text("INSERT INTO asset (ticker, name, currency) VALUES ('ABC','A','EUR')")
        )
        connection.execute(text(INSERT_V1.format(quantity=1, currency="USD")))

    with pytest.raises(RuntimeError, match="different from their asset"):
        init_db(engine)

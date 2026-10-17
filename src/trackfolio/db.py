"""Database engine and schema migrations (SQLite by default, PostgreSQL via URL)."""

import sqlite3
from contextlib import closing
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, event, inspect
from sqlmodel import Session, create_engine

from trackfolio.config import DATA_DIR, DATABASE_URL

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
BASELINE_REVISION = "0001"


def _set_pragmas(dbapi_connection: Any, _record: object) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def configure_engine(engine: Engine) -> Engine:
    """Enable foreign keys, WAL and a busy timeout on every new SQLite connection."""
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _set_pragmas)
    return engine


@cache
def get_engine() -> Engine:
    """Create the engine (and the SQLite data directory) on first use."""
    if DATABASE_URL.startswith("sqlite"):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return configure_engine(
            create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
        )
    return create_engine(DATABASE_URL)


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def _backup_sqlite(engine: Engine) -> None:
    """Copy a file-based SQLite database next to itself before it is migrated."""
    database = engine.url.database
    if engine.dialect.name != "sqlite" or not database or database == ":memory:":
        return
    source = Path(database)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = source.with_name(f"{source.name}.pre-migration-{stamp}")
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)  # consistent copy, including content still in the WAL


def init_db(engine: Engine | None = None) -> None:
    """Bring the schema to the latest revision.

    A database created before migrations existed (tables but no recorded revision) is
    marked as the baseline revision before upgrading. A non-empty SQLite file is backed up
    before every migration.
    """
    engine = engine or get_engine()
    config = _alembic_config()
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    tables = inspect(engine).get_table_names()
    legacy = revision is None and "transaction" in tables
    if tables and revision != ScriptDirectory.from_config(config).get_current_head():
        _backup_sqlite(engine)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        if legacy:
            command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")


def get_session() -> Session:
    """Create a database session for one unit of work."""
    return Session(get_engine())

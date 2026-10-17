"""SQLite engine and schema initialization."""

from functools import cache
from typing import Any

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

from trackfolio.config import DATA_DIR, DATABASE_URL


def _set_pragmas(dbapi_connection: Any, _record: object) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def configure_engine(engine: Engine) -> Engine:
    """Enable foreign keys, WAL and a busy timeout on every new SQLite connection."""
    event.listen(engine, "connect", _set_pragmas)
    return engine


@cache
def get_engine() -> Engine:
    """Create the engine (and the data directory) on first use."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return configure_engine(create_engine(DATABASE_URL, connect_args={"check_same_thread": False}))


def init_db() -> None:
    """Create the local database schema when it does not exist."""
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Session:
    """Create a database session for one unit of work."""
    return Session(get_engine())

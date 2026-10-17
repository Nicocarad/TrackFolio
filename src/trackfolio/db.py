"""SQLite engine and schema initialization."""

from sqlmodel import Session, SQLModel, create_engine

from trackfolio.config import DATA_DIR, DATABASE_URL

DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    """Create the local database schema when it does not exist."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    """Create a database session for one unit of work."""
    return Session(engine)

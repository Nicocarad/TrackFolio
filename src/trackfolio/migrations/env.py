"""Alembic environment: uses the application's database URL and SQLModel metadata."""

from alembic import context
from sqlalchemy import Connection
from sqlmodel import SQLModel

import trackfolio.models  # noqa: F401  (register tables on the metadata)
from trackfolio.config import get_settings
from trackfolio.db import get_engine

target_metadata = SQLModel.metadata


def _configure(connection: Connection | None) -> None:
    context.configure(
        connection=connection,
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=connection is None,
        render_as_batch=True,
    )


def run_migrations() -> None:
    """Run against the connection passed by ``init_db`` or a fresh engine for the CLI."""
    if context.is_offline_mode():
        _configure(None)
        with context.begin_transaction():
            context.run_migrations()
        return
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    with get_engine().connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()

"""Add the rate limiter events and the persistent instrument search cache."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_event_kind", "rate_event", ["kind"])
    op.create_index("ix_rate_event_key", "rate_event", ["key"])
    op.create_table(
        "instrument_cache",
        sa.Column("query_key", sa.String(), nullable=False),
        sa.Column("payload", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("query_key"),
    )


def downgrade() -> None:
    op.drop_table("instrument_cache")
    op.drop_table("rate_event")

"""Add the SPLIT and DIVIDEND transaction types."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'SPLIT'")
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'DIVIDEND'")
    else:  # SQLite stores the enum as VARCHAR(4): widen it to match the model
        with op.batch_alter_table("transaction") as batch:
            batch.alter_column(
                "type",
                existing_type=sa.Enum("BUY", "SELL", name="transactiontype"),
                type_=sa.Enum("BUY", "SELL", "SPLIT", "DIVIDEND", name="transactiontype"),
                existing_nullable=False,
            )


def downgrade() -> None:
    # PostgreSQL cannot drop enum values; they stay unused. Rows using them are not removed.
    pass

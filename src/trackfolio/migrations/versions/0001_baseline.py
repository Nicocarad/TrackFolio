"""Baseline schema as created before migrations existed (no CHECK constraints)."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset",
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("isin", sa.String(), nullable=True),
        sa.Column("exchange", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("asset_class", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("ticker"),
    )
    op.create_index("ix_asset_isin", "asset", ["isin"])
    op.create_index("ix_asset_ticker", "asset", ["ticker"])
    op.create_table(
        "price",
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ticker", "date"),
    )
    op.create_table(
        "transaction",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("type", sa.Enum("BUY", "SELL", name="transactiontype"), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("fees", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["ticker"], ["asset.ticker"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transaction_date", "transaction", ["date"])
    op.create_index("ix_transaction_ticker", "transaction", ["ticker"])


def downgrade() -> None:
    op.drop_table("transaction")
    op.drop_table("price")
    op.drop_table("asset")
    sa.Enum(name="transactiontype").drop(op.get_bind(), checkfirst=True)

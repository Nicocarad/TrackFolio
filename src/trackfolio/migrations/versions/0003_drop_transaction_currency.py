"""Drop transaction.currency; the currency is the asset's."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    mismatched = (
        op.get_bind()
        .execute(
            sa.text(
                'SELECT count(*) FROM "transaction" t JOIN asset a ON a.ticker = t.ticker '
                "WHERE upper(t.currency) <> upper(a.currency)"
            )
        )
        .scalar()
    )
    if mismatched:
        raise RuntimeError(
            f"{mismatched} transactions have a currency different from their asset's; "
            "fix them before migrating"
        )
    with op.batch_alter_table("transaction") as batch:
        batch.drop_column("currency")


def downgrade() -> None:
    with op.batch_alter_table("transaction") as batch:
        batch.add_column(sa.Column("currency", sa.String(length=3), nullable=True))
    op.execute(
        'UPDATE "transaction" SET currency = '
        '(SELECT currency FROM asset WHERE asset.ticker = "transaction".ticker)'
    )
    with op.batch_alter_table("transaction") as batch:
        batch.alter_column("currency", existing_type=sa.String(length=3), nullable=False)

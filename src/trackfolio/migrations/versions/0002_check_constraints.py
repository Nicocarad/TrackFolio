"""Add CHECK constraints on quantity, price, fees and close."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transaction") as batch:
        batch.create_check_constraint("ck_transaction_quantity", "quantity > 0")
        batch.create_check_constraint("ck_transaction_price", "price >= 0")
        batch.create_check_constraint("ck_transaction_fees", "fees >= 0")
    with op.batch_alter_table("price") as batch:
        batch.create_check_constraint("ck_price_close", "close >= 0")


def downgrade() -> None:
    with op.batch_alter_table("transaction") as batch:
        batch.drop_constraint("ck_transaction_quantity", type_="check")
        batch.drop_constraint("ck_transaction_price", type_="check")
        batch.drop_constraint("ck_transaction_fees", type_="check")
    with op.batch_alter_table("price") as batch:
        batch.drop_constraint("ck_price_close", type_="check")

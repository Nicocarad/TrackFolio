"""Add the user table and make every transaction belong to a user.

Existing transactions are assigned to a placeholder admin that cannot log in until its
password is set with ``trackfolio set-password`` (and renamed with ``change-email``).
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

PLACEHOLDER_EMAIL = "admin@trackfolio.local"
UNUSABLE_HASH = "!"


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)
    with op.batch_alter_table("transaction") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    if bind.execute(sa.text('SELECT count(*) FROM "transaction"')).scalar():
        insert = sa.text(
            'INSERT INTO "user" (email, password_hash, is_admin, created_at) '
            "VALUES (:email, :hash, :admin, :now)"
        ).bindparams(sa.bindparam("now", type_=sa.DateTime()))
        bind.execute(
            insert,
            {
                "email": PLACEHOLDER_EMAIL,
                "hash": UNUSABLE_HASH,
                "admin": True,
                "now": datetime.now(UTC).replace(tzinfo=None),
            },
        )
        bind.execute(
            sa.text(
                'UPDATE "transaction" SET user_id = (SELECT id FROM "user" WHERE email = :email)'
            ),
            {"email": PLACEHOLDER_EMAIL},
        )

    with op.batch_alter_table("transaction") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_transaction_user", "user", ["user_id"], ["id"])
        batch.create_index("ix_transaction_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("transaction") as batch:
        batch.drop_index("ix_transaction_user_id")
        batch.drop_constraint("fk_transaction_user", type_="foreignkey")
        batch.drop_column("user_id")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_table("user")

"""Add secure transfer constraints and indexes

Revision ID: f8c2d1e7a6b4
Revises: e5b7a2c9d4f1
Create Date: 2026-07-24 00:00:00.000000

"""

from alembic import op


revision = "f8c2d1e7a6b4"
down_revision = "e5b7a2c9d4f1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("transfers") as batch_op:
        batch_op.drop_constraint("ck_transfers_amount_positive", type_="check")
        batch_op.create_check_constraint(
            "ck_transfers_amount_range",
            "amount BETWEEN 1 AND 1000000000",
        )
        batch_op.create_check_constraint(
            "ck_transfers_idempotency_key_format",
            "length(idempotency_key) = 64 AND idempotency_key NOT GLOB '*[^0-9a-f]*'",
        )

    op.create_index(
        "ix_transfers_sender_created",
        "transfers",
        ["sender_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_transfers_recipient_created",
        "transfers",
        ["recipient_id", "created_at", "id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_transfers_recipient_created", table_name="transfers")
    op.drop_index("ix_transfers_sender_created", table_name="transfers")

    with op.batch_alter_table("transfers") as batch_op:
        batch_op.drop_constraint(
            "ck_transfers_idempotency_key_format",
            type_="check",
        )
        batch_op.drop_constraint("ck_transfers_amount_range", type_="check")
        batch_op.create_check_constraint(
            "ck_transfers_amount_positive",
            "amount > 0",
        )

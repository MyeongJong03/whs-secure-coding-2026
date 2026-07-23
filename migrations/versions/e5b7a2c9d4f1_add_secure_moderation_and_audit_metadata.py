"""Add secure moderation and audit metadata

Revision ID: e5b7a2c9d4f1
Revises: a91f4c8d2e70
Create Date: 2026-07-23 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "e5b7a2c9d4f1"
down_revision = "a91f4c8d2e70"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column("moderation_previous_status", sa.String(length=16), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_products_moderation_previous_status",
            "moderation_previous_status IS NULL "
            "OR moderation_previous_status IN ('active', 'sold')",
        )

    with op.batch_alter_table("reports") as batch_op:
        batch_op.add_column(
            sa.Column("reviewed_by_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch_op.create_foreign_key(
            "fk_reports_reviewed_by_id_users",
            "users",
            ["reviewed_by_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_reports_review_consistency",
            "(status = 'pending' AND reviewed_by_id IS NULL AND reviewed_at IS NULL) "
            "OR (status IN ('confirmed', 'rejected') "
            "AND reviewed_by_id IS NOT NULL AND reviewed_at IS NOT NULL)",
        )

    op.create_index(
        "ix_reports_target_status_created",
        "reports",
        ["target_type", "target_id", "status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_reports_reporter_created",
        "reports",
        ["reporter_id", "created_at", "id"],
        unique=False,
    )

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.create_check_constraint(
            "ck_audit_logs_action_length",
            "length(action) BETWEEN 1 AND 100",
        )
        batch_op.create_check_constraint(
            "ck_audit_logs_target_type_length",
            "length(target_type) BETWEEN 1 AND 50",
        )

    op.create_index(
        "ix_audit_logs_created",
        "audit_logs",
        ["created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_actor_created",
        "audit_logs",
        ["actor_user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_target_created",
        "audit_logs",
        ["target_type", "target_id", "created_at", "id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_audit_logs_target_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created", table_name="audit_logs")
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_constraint("ck_audit_logs_target_type_length", type_="check")
        batch_op.drop_constraint("ck_audit_logs_action_length", type_="check")

    op.drop_index("ix_reports_reporter_created", table_name="reports")
    op.drop_index("ix_reports_target_status_created", table_name="reports")
    with op.batch_alter_table("reports") as batch_op:
        batch_op.drop_constraint("ck_reports_review_consistency", type_="check")
        batch_op.drop_constraint("fk_reports_reviewed_by_id_users", type_="foreignkey")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by_id")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint(
            "ck_products_moderation_previous_status", type_="check"
        )
        batch_op.drop_column("moderation_previous_status")

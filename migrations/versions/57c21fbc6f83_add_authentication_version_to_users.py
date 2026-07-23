"""Add authentication version to users

Revision ID: 57c21fbc6f83
Revises: 09357cac1cb7
Create Date: 2026-07-23 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "57c21fbc6f83"
down_revision = "09357cac1cb7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auth_version",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_users_auth_version_positive", "auth_version >= 1"
        )


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_auth_version_positive", type_="check")
        batch_op.drop_column("auth_version")

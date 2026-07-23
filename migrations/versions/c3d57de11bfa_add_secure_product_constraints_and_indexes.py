"""Add secure product constraints and indexes

Revision ID: c3d57de11bfa
Revises: 57c21fbc6f83
Create Date: 2026-07-23 00:00:00.000000

"""

from alembic import op


revision = "c3d57de11bfa"
down_revision = "57c21fbc6f83"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint("ck_products_price_positive", type_="check")
        batch_op.create_check_constraint(
            "ck_products_price_range", "price BETWEEN 1 AND 1000000000"
        )
        batch_op.create_unique_constraint(
            "uq_products_image_filename", ["image_filename"]
        )

    op.create_index(
        "ix_products_public_status_created",
        "products",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_products_seller_status_updated",
        "products",
        ["seller_id", "status", "updated_at"],
        unique=False,
    )
    op.create_index("ix_products_price", "products", ["price"], unique=False)


def downgrade():
    op.drop_index("ix_products_price", table_name="products")
    op.drop_index("ix_products_seller_status_updated", table_name="products")
    op.drop_index("ix_products_public_status_created", table_name="products")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint("uq_products_image_filename", type_="unique")
        batch_op.drop_constraint("ck_products_price_range", type_="check")
        batch_op.create_check_constraint("ck_products_price_positive", "price > 0")

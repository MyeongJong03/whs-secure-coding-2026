"""Add secure chat constraints and indexes

Revision ID: a91f4c8d2e70
Revises: c3d57de11bfa
Create Date: 2026-07-23 00:00:00.000000

"""

from alembic import op


revision = "a91f4c8d2e70"
down_revision = "c3d57de11bfa"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.create_check_constraint(
            "ck_chat_messages_is_hidden_boolean", "is_hidden IN (0, 1)"
        )

    op.create_index(
        "ix_chat_messages_conversation_visible_created",
        "chat_messages",
        ["conversation_id", "is_hidden", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_messages_sender_created",
        "chat_messages",
        ["sender_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_direct_conversations_user1_created",
        "direct_conversations",
        ["user1_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_direct_conversations_user2_created",
        "direct_conversations",
        ["user2_id", "created_at", "id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_direct_conversations_user2_created",
        table_name="direct_conversations",
    )
    op.drop_index(
        "ix_direct_conversations_user1_created",
        table_name="direct_conversations",
    )
    op.drop_index(
        "ix_chat_messages_sender_created",
        table_name="chat_messages",
    )
    op.drop_index(
        "ix_chat_messages_conversation_visible_created",
        table_name="chat_messages",
    )

    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_constraint("ck_chat_messages_is_hidden_boolean", type_="check")

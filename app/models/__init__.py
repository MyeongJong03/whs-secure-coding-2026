import uuid
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def new_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(
            "length(username) BETWEEN 4 AND 32", name="ck_users_username_length"
        ),
        db.CheckConstraint(
            "username NOT GLOB '*[^A-Za-z0-9_]*'",
            name="ck_users_username_characters",
        ),
        db.CheckConstraint("length(bio) <= 500", name="ck_users_bio_length"),
        db.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        db.CheckConstraint("status IN ('active', 'dormant')", name="ck_users_status"),
        db.CheckConstraint("auth_version >= 1", name="ck_users_auth_version_positive"),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_uuid)
    username = db.Column(db.String(32), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(
        db.String(500), nullable=False, default="", server_default=db.text("''")
    )
    role = db.Column(
        db.String(16),
        nullable=False,
        default="user",
        server_default=db.text("'user'"),
    )
    status = db.Column(
        db.String(16),
        nullable=False,
        default="active",
        server_default=db.text("'active'"),
    )
    auth_version = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default=db.text("1"),
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    wallet = db.relationship(
        "Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def set_password(self, candidate: str) -> None:
        self.password_hash = generate_password_hash(candidate, method="scrypt")

    def check_password(self, candidate: str) -> bool:
        return check_password_hash(self.password_hash, candidate)

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class Wallet(db.Model):
    __tablename__ = "wallets"
    __table_args__ = (
        db.CheckConstraint("balance >= 0", name="ck_wallets_balance_nonnegative"),
    )

    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    balance = db.Column(
        db.Integer,
        nullable=False,
        default=100000,
        server_default=db.text("100000"),
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user = db.relationship("User", back_populates="wallet")


class Product(db.Model):
    __tablename__ = "products"
    __table_args__ = (
        db.CheckConstraint(
            "length(title) BETWEEN 1 AND 100", name="ck_products_title_length"
        ),
        db.CheckConstraint(
            "length(description) BETWEEN 1 AND 2000",
            name="ck_products_description_length",
        ),
        db.CheckConstraint(
            "price BETWEEN 1 AND 1000000000", name="ck_products_price_range"
        ),
        db.CheckConstraint(
            "status IN ('active', 'hidden', 'sold', 'deleted')",
            name="ck_products_status",
        ),
        db.CheckConstraint(
            "moderation_previous_status IS NULL "
            "OR moderation_previous_status IN ('active', 'sold')",
            name="ck_products_moderation_previous_status",
        ),
        db.UniqueConstraint("image_filename", name="uq_products_image_filename"),
        db.Index("ix_products_public_status_created", "status", "created_at"),
        db.Index(
            "ix_products_seller_status_updated",
            "seller_id",
            "status",
            "updated_at",
        ),
        db.Index("ix_products_price", "price"),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_uuid)
    seller_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(
        db.String(16),
        nullable=False,
        default="active",
        server_default=db.text("'active'"),
    )
    moderation_previous_status = db.Column(db.String(16), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    seller = db.relationship("User", foreign_keys=[seller_id])


class Report(db.Model):
    __tablename__ = "reports"
    __table_args__ = (
        db.UniqueConstraint(
            "reporter_id", "target_type", "target_id", name="uq_reports_reporter_target"
        ),
        db.CheckConstraint(
            "target_type IN ('user', 'product')", name="ck_reports_target_type"
        ),
        db.CheckConstraint(
            "length(reason) BETWEEN 10 AND 500", name="ck_reports_reason_length"
        ),
        db.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')", name="ck_reports_status"
        ),
        db.CheckConstraint(
            "(status = 'pending' AND reviewed_by_id IS NULL AND reviewed_at IS NULL) "
            "OR (status IN ('confirmed', 'rejected') "
            "AND reviewed_by_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_reports_review_consistency",
        ),
        db.Index(
            "ix_reports_target_status_created",
            "target_type",
            "target_id",
            "status",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_reports_reporter_created",
            "reporter_id",
            "created_at",
            "id",
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_uuid)
    reporter_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_type = db.Column(db.String(16), nullable=False)
    target_id = db.Column(db.String(36), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(
        db.String(16),
        nullable=False,
        default="pending",
        server_default=db.text("'pending'"),
    )
    reviewed_by_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
        onupdate=utc_now,
    )

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_id])


class DirectConversation(db.Model):
    __tablename__ = "direct_conversations"
    __table_args__ = (
        db.UniqueConstraint(
            "user1_id", "user2_id", name="uq_direct_conversations_users"
        ),
        db.CheckConstraint(
            "user1_id < user2_id", name="ck_direct_conversations_canonical_order"
        ),
        db.Index(
            "ix_direct_conversations_user1_created", "user1_id", "created_at", "id"
        ),
        db.Index(
            "ix_direct_conversations_user2_created", "user2_id", "created_at", "id"
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_uuid)
    user1_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user2_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    user1 = db.relationship("User", foreign_keys=[user1_id])
    user2 = db.relationship("User", foreign_keys=[user2_id])


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    __table_args__ = (
        db.CheckConstraint(
            "length(body) BETWEEN 1 AND 500", name="ck_chat_messages_body_length"
        ),
        db.CheckConstraint(
            "is_hidden IN (0, 1)", name="ck_chat_messages_is_hidden_boolean"
        ),
        db.Index(
            "ix_chat_messages_conversation_visible_created",
            "conversation_id",
            "is_hidden",
            "created_at",
            "id",
        ),
        db.Index("ix_chat_messages_sender_created", "sender_id", "created_at", "id"),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_uuid)
    sender_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id = db.Column(
        db.String(36),
        db.ForeignKey("direct_conversations.id", ondelete="CASCADE"),
        nullable=True,
    )
    body = db.Column(db.String(500), nullable=False)
    is_hidden = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("0")
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    sender = db.relationship("User", foreign_keys=[sender_id])
    conversation = db.relationship("DirectConversation", foreign_keys=[conversation_id])


class Transfer(db.Model):
    __tablename__ = "transfers"
    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_transfers_amount_positive"),
        db.CheckConstraint(
            "sender_id <> recipient_id", name="ck_transfers_distinct_users"
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_uuid)
    sender_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recipient_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    amount = db.Column(db.Integer, nullable=False)
    idempotency_key = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (
        db.CheckConstraint(
            "length(action) BETWEEN 1 AND 100",
            name="ck_audit_logs_action_length",
        ),
        db.CheckConstraint(
            "length(target_type) BETWEEN 1 AND 50",
            name="ck_audit_logs_target_type_length",
        ),
        db.Index("ix_audit_logs_created", "created_at", "id"),
        db.Index(
            "ix_audit_logs_actor_created",
            "actor_user_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_audit_logs_target_created",
            "target_type",
            "target_id",
            "created_at",
            "id",
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_uuid)
    actor_user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.String(36), nullable=True)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    actor = db.relationship("User", foreign_keys=[actor_user_id])

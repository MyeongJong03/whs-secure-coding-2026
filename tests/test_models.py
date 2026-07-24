import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import DirectConversation, Product, Report, Transfer, User, Wallet


def add_user(username: str) -> User:
    user = User(username=username, password_hash="stored-hash-value")
    db.session.add(user)
    db.session.commit()
    return user


def assert_commit_rejected() -> None:
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_sqlite_foreign_keys_are_enabled(app):
    with app.app_context():
        enabled = db.session.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert enabled == 1


def test_username_unique_constraint(app):
    with app.app_context():
        add_user("alice")
        db.session.add(User(username="alice", password_hash="another-stored-hash"))
        assert_commit_rejected()


@pytest.mark.parametrize("username", ["한글이름", "bad-name", "bad name"])
def test_username_rejects_nonpolicy_characters(app, username):
    with app.app_context():
        db.session.add(User(username=username, password_hash="stored-hash-value"))
        assert_commit_rejected()


def test_wallet_rejects_negative_balance(app):
    with app.app_context():
        user = add_user("alice")
        db.session.add(Wallet(user_id=user.id, balance=-1))
        assert_commit_rejected()


def test_wallet_uses_initial_balance(app):
    with app.app_context():
        user = add_user("alice")
        wallet = Wallet(user_id=user.id)
        db.session.add(wallet)
        db.session.commit()

        assert wallet.balance == 100000


@pytest.mark.parametrize("price", [0, -1])
def test_product_rejects_nonpositive_price(app, price):
    with app.app_context():
        seller = add_user("alice")
        db.session.add(
            Product(
                seller_id=seller.id,
                title="상품",
                description="정상적인 상품 설명",
                price=price,
            )
        )
        assert_commit_rejected()


def test_report_duplicate_constraint(app):
    with app.app_context():
        reporter = add_user("alice")
        target_id = str(uuid.uuid4())
        first = Report(
            reporter_id=reporter.id,
            target_type="product",
            target_id=target_id,
            reason="충분히 구체적인 신고 사유입니다",
        )
        db.session.add(first)
        db.session.commit()
        db.session.add(
            Report(
                reporter_id=reporter.id,
                target_type="product",
                target_id=target_id,
                reason="다시 제출한 신고 사유입니다",
            )
        )
        assert_commit_rejected()


@pytest.mark.parametrize("amount", [0, -1])
def test_transfer_rejects_nonpositive_amount(app, amount):
    with app.app_context():
        sender = add_user("alice")
        recipient = add_user("bobby")
        db.session.add(
            Transfer(
                sender_id=sender.id,
                recipient_id=recipient.id,
                amount=amount,
                idempotency_key="a" * 64,
            )
        )
        assert_commit_rejected()


def test_transfer_rejects_same_sender_and_recipient(app):
    with app.app_context():
        user = add_user("alice")
        db.session.add(
            Transfer(
                sender_id=user.id,
                recipient_id=user.id,
                amount=1,
                idempotency_key="a" * 64,
            )
        )
        assert_commit_rejected()


def test_direct_conversation_rejects_same_user(app):
    with app.app_context():
        user = add_user("alice")
        db.session.add(DirectConversation(user1_id=user.id, user2_id=user.id))
        assert_commit_rejected()


def test_direct_conversation_accepts_sorted_canonical_pair(app):
    with app.app_context():
        first_user = add_user("alice")
        second_user = add_user("bobby")
        user1_id, user2_id = sorted((first_user.id, second_user.id))
        db.session.add(DirectConversation(user1_id=user1_id, user2_id=user2_id))
        db.session.commit()

        conversation = db.session.execute(db.select(DirectConversation)).scalar_one()

        assert conversation.user1_id == user1_id
        assert conversation.user2_id == user2_id


def test_direct_conversation_rejects_duplicate_canonical_pair(app):
    with app.app_context():
        first_user = add_user("alice")
        second_user = add_user("bobby")
        user1_id, user2_id = sorted((first_user.id, second_user.id))
        db.session.add(DirectConversation(user1_id=user1_id, user2_id=user2_id))
        db.session.commit()
        db.session.add(DirectConversation(user1_id=user1_id, user2_id=user2_id))
        assert_commit_rejected()


def test_direct_conversation_rejects_reverse_order_at_database(app):
    with app.app_context():
        first_user = add_user("alice")
        second_user = add_user("bobby")
        user1_id, user2_id = sorted((first_user.id, second_user.id))
        db.session.add(DirectConversation(user1_id=user2_id, user2_id=user1_id))
        assert_commit_rejected()


def test_active_user_is_active():
    user = User(username="alice", password_hash="stored-hash-value", status="active")

    assert user.is_active is True


def test_dormant_user_is_not_active():
    user = User(username="alice", password_hash="stored-hash-value", status="dormant")

    assert user.is_active is False


def test_user_model_has_no_plaintext_password_column():
    assert "password" not in User.__table__.columns
    assert "password_hash" in User.__table__.columns


def test_password_hash_uses_werkzeug_scrypt_default():
    user = User(username="alice")
    user.set_password("a-valid-test-password")

    assert user.password_hash.startswith("scrypt:")
    assert user.password_hash != "a-valid-test-password"
    assert user.check_password("a-valid-test-password") is True

import hashlib
import re
import secrets
import stat
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

import pytest
from limits.storage import memory as memory_storage
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app
from app.extensions import db, limiter
from app.filesystem import secure_instance_directory, secure_sqlite_database_file
from app.models import AuditLog, Transfer, User, Wallet
from app.wallet import routes as wallet_routes
from app.wallet import services as wallet_services
from app.wallet.policy import derive_idempotency_key
from app.wallet.services import (
    TransferOutcome,
    TransferResult,
    create_transfer,
    get_transfer_detail,
    list_transfer_history,
)
from app.wallet.views import (
    TransferDetailView,
    TransferHistoryPage,
    TransferHistoryView,
    WalletSummaryView,
)


PASSWORD = "valid-test-password-123"
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)


def login(client, login_client, username="alice", password=PASSWORD):
    response = login_client(client, username=username, password=password)
    assert response.status_code == 303
    return response


def named_input(response, name):
    match = re.search(
        rf'<input[^>]*name="{re.escape(name)}"[^>]*value="([^"]*)"'.encode(),
        response.data,
    )
    assert match is not None
    return match.group(1).decode()


def transfer_form_tokens(client):
    response = client.get("/wallet/transfer")
    assert response.status_code == 200
    return (
        named_input(response, "csrf_token"),
        named_input(response, "idempotency_token"),
        response,
    )


def submit_transfer(
    client,
    *,
    recipient="bobby",
    amount="100",
    password=PASSWORD,
    csrf_token=None,
    idempotency_token=None,
    extra=None,
):
    if csrf_token is None or idempotency_token is None:
        generated_csrf, generated_idempotency, _response = transfer_form_tokens(client)
        csrf_token = csrf_token or generated_csrf
        idempotency_token = idempotency_token or generated_idempotency
    data = {
        "recipient_username": recipient,
        "amount": amount,
        "current_password": password,
        "csrf_token": csrf_token,
        "idempotency_token": idempotency_token,
    }
    data.update(extra or {})
    return client.post("/wallet/transfer", data=data)


def wallet_balances(*user_ids):
    return tuple(
        db.session.execute(
            db.select(Wallet.balance).where(Wallet.user_id == user_id)
        ).scalar_one()
        for user_id in user_ids
    )


def seed_transfer(sender_id, recipient_id, amount, *, created_at=None, key=None):
    transfer = Transfer(
        sender_id=sender_id,
        recipient_id=recipient_id,
        amount=amount,
        idempotency_key=key or secrets.token_hex(32),
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.session.add(transfer)
    db.session.commit()
    return transfer.id


def assert_empty_transfer_state():
    assert db.session.execute(db.select(Transfer.id)).all() == []
    assert db.session.execute(db.select(AuditLog.id)).all() == []


def test_wallet_routes_require_authentication(client):
    assert client.get("/wallet").status_code == 302
    assert client.get("/wallet/transfer").status_code == 302
    assert client.get(f"/wallet/transfers/{uuid4()}").status_code == 302


def test_wallet_index_and_transfer_form_are_private_virtual_point_pages(
    client, user_factory, login_client
):
    user_factory("alice")
    login(client, login_client)

    for path in ("/wallet", "/wallet/transfer"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store, private"
        html = response.get_data(as_text=True)
        assert "과제용 가상 포인트" in html
        assert "실제 금융 자산" in html
        assert "현금 또는 결제 수단이 아닙니다" in html
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_two_transfer_gets_generate_distinct_hidden_urlsafe_tokens(
    client, user_factory, login_client, caplog
):
    user_factory("alice")
    login(client, login_client)

    first = client.get("/wallet/transfer")
    second = client.get("/wallet/transfer")
    first_token = named_input(first, "idempotency_token")
    second_token = named_input(second, "idempotency_token")

    assert first_token != second_token
    assert TOKEN_PATTERN.fullmatch(first_token)
    assert TOKEN_PATTERN.fullmatch(second_token)
    assert first.data.count(first_token.encode()) == 1
    assert b'name="idempotency_token"' in first.data
    assert b'type="hidden"' in first.data
    parser = VisibleTextParser()
    parser.feed(first.get_data(as_text=True))
    assert first_token not in "".join(parser.text)
    assert first_token not in caplog.text


def test_derived_key_is_sender_bound_lowercase_sha256():
    token = secrets.token_urlsafe(32)
    sender_id = str(uuid4())

    derived = derive_idempotency_key(sender_id, token)

    assert derived == hashlib.sha256(f"{sender_id}:{token}".encode()).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", derived)
    assert derive_idempotency_key(str(uuid4()), token) != derived


@pytest.mark.parametrize(
    "token",
    [
        "",
        "a" * 42,
        "a" * 44,
        ("a" * 42) + "+",
        ("a" * 42) + "/",
        ("a" * 42) + "=",
    ],
)
def test_transfer_post_rejects_invalid_token_without_reflecting_it(
    client, user_factory, login_client, token
):
    user_factory("alice")
    user_factory("bobby")
    login(client, login_client)
    csrf, _valid_token, _response = transfer_form_tokens(client)

    response = submit_transfer(
        client,
        csrf_token=csrf,
        idempotency_token=token,
    )

    assert response.status_code == 400
    if token:
        assert token.encode() not in response.data
    with client.application.app_context():
        assert_empty_transfer_state()


def test_transfer_post_requires_csrf_and_is_private(client, user_factory, login_client):
    user_factory("alice")
    user_factory("bobby")
    login(client, login_client)

    response = client.post(
        "/wallet/transfer",
        data={
            "recipient_username": "bobby",
            "amount": "100",
            "current_password": PASSWORD,
            "idempotency_token": secrets.token_urlsafe(32),
        },
    )

    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "no-store, private"


def test_successful_transfer_is_atomic_redirects_303_and_redacts_secrets(
    app, client, user_factory, login_client
):
    sender = user_factory("alice", balance=1000)
    recipient = user_factory("bobby", balance=250)
    login(client, login_client)
    csrf, token, _response = transfer_form_tokens(client)

    response = submit_transfer(
        client,
        recipient="  bobby  ",
        amount="300",
        csrf_token=csrf,
        idempotency_token=token,
    )

    assert response.status_code == 303
    assert re.fullmatch(r"/wallet/transfers/[0-9a-f-]{36}", response.location)
    assert token not in response.location
    assert PASSWORD not in response.location
    with app.app_context():
        assert wallet_balances(sender.id, recipient.id) == (700, 550)
        transfer = db.session.execute(db.select(Transfer)).scalar_one()
        assert (transfer.sender_id, transfer.recipient_id, transfer.amount) == (
            sender.id,
            recipient.id,
            300,
        )
        expected_key = derive_idempotency_key(sender.id, token)
        assert transfer.idempotency_key == expected_key
        assert transfer.idempotency_key != token
        audit = db.session.execute(
            db.select(AuditLog).where(AuditLog.action == "transfer.created")
        ).scalar_one()
        assert audit.actor_user_id == sender.id
        assert audit.target_type == "transfer"
        assert audit.target_id == transfer.id
        assert audit.details == {"amount": 300}
        serialized = repr(audit.details)
        assert token not in serialized and expected_key not in serialized
        assert (
            sum(db.session.execute(db.select(Wallet.balance)).scalars().all()) == 1250
        )


def test_active_admins_can_send_and_receive(app, user_factory):
    sender = user_factory("admin_sender", role="admin", balance=500)
    recipient = user_factory("admin_recipient", role="admin", balance=500)
    with app.app_context():
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=125,
            current_password=PASSWORD,
            raw_idempotency_token=secrets.token_urlsafe(32),
        )
        assert outcome.result is TransferResult.CREATED
        assert wallet_balances(sender.id, recipient.id) == (375, 625)


@pytest.mark.parametrize("amount", ["0", "-1", "1.5", "1000000001"])
def test_transfer_form_rejects_invalid_amounts(
    app, client, user_factory, login_client, amount
):
    sender = user_factory("alice", balance=2000)
    recipient = user_factory("bobby", balance=2000)
    login(client, login_client)

    response = submit_transfer(client, amount=amount)

    assert response.status_code == 400
    with app.app_context():
        assert wallet_balances(sender.id, recipient.id) == (2000, 2000)
        assert_empty_transfer_state()


@pytest.mark.parametrize("amount", [True, False, 1.5, "1", 0, 1_000_000_001])
def test_service_revalidates_non_integer_and_range_amounts(app, user_factory, amount):
    sender = user_factory("alice")
    recipient = user_factory("bobby")
    with app.app_context():
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=amount,
            current_password=PASSWORD,
            raw_idempotency_token=secrets.token_urlsafe(32),
        )
        assert outcome.result is TransferResult.DATABASE_ERROR
        assert wallet_balances(sender.id, recipient.id) == (100000, 100000)
        assert_empty_transfer_state()


def test_wrong_current_password_is_not_reflected_and_changes_nothing(
    app, client, user_factory, login_client
):
    sender = user_factory("alice", balance=500)
    recipient = user_factory("bobby", balance=500)
    login(client, login_client)
    submitted_password = "wrong-current-password-marker"

    response = submit_transfer(client, password=submitted_password)

    assert response.status_code == 400
    assert "현재 비밀번호가 올바르지 않습니다." in response.get_data(as_text=True)
    assert submitted_password.encode() not in response.data
    with app.app_context():
        assert wallet_balances(sender.id, recipient.id) == (500, 500)
        assert_empty_transfer_state()


def test_current_password_is_not_stripped(app, user_factory):
    spaced_password = "  spaced-valid-password-123  "
    sender = user_factory("alice", password=spaced_password, balance=500)
    recipient = user_factory("bobby", balance=500)
    with app.app_context():
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=100,
            current_password=spaced_password,
            raw_idempotency_token=secrets.token_urlsafe(32),
        )
        assert outcome.result is TransferResult.CREATED
        assert wallet_balances(sender.id, recipient.id) == (400, 600)


@pytest.mark.parametrize("recipient_name", ["missing", "sleeping"])
def test_missing_and_dormant_recipients_use_safe_error(
    app, client, user_factory, login_client, recipient_name
):
    sender = user_factory("alice", balance=500)
    if recipient_name == "sleeping":
        recipient = user_factory("sleeping", status="dormant", balance=500)
    else:
        recipient = None
    login(client, login_client)

    response = submit_transfer(client, recipient=recipient_name)

    assert response.status_code == 400
    assert "수신자를 확인할 수 없습니다." in response.get_data(as_text=True)
    assert b"constraint" not in response.data.lower()
    assert b"traceback" not in response.data.lower()
    with app.app_context():
        assert (
            db.session.execute(
                db.select(Wallet.balance).where(Wallet.user_id == sender.id)
            ).scalar_one()
            == 500
        )
        if recipient is not None:
            assert wallet_balances(recipient.id) == (500,)
        assert_empty_transfer_state()


def test_self_transfer_is_rejected_without_state_change(
    app, client, user_factory, login_client
):
    sender = user_factory("alice", balance=500)
    login(client, login_client)

    response = submit_transfer(client, recipient="alice")

    assert response.status_code == 400
    assert "자기 자신에게 송금할 수 없습니다." in response.get_data(as_text=True)
    with app.app_context():
        assert wallet_balances(sender.id) == (500,)
        assert_empty_transfer_state()


def test_insufficient_funds_rolls_back_ledger_credit_and_audit(
    app, client, user_factory, login_client
):
    sender = user_factory("alice", balance=100)
    recipient = user_factory("bobby", balance=200)
    login(client, login_client)

    response = submit_transfer(client, amount="101")

    assert response.status_code == 400
    assert "잔액이 부족합니다." in response.get_data(as_text=True)
    with app.app_context():
        assert wallet_balances(sender.id, recipient.id) == (100, 200)
        assert_empty_transfer_state()


def test_extra_mass_assignment_fields_are_ignored(
    app, client, user_factory, login_client
):
    sender = user_factory("alice", balance=500)
    recipient = user_factory("bobby", balance=500)
    attacker = user_factory("mallory", balance=500)
    login(client, login_client)

    response = submit_transfer(
        client,
        amount="100",
        extra={
            "sender_id": attacker.id,
            "recipient_id": attacker.id,
            "balance": "999999999",
            "idempotency_key": "f" * 64,
        },
    )

    assert response.status_code == 303
    with app.app_context():
        assert wallet_balances(sender.id, recipient.id, attacker.id) == (400, 600, 500)
        transfer = db.session.execute(db.select(Transfer)).scalar_one()
        assert transfer.sender_id == sender.id
        assert transfer.recipient_id == recipient.id
        assert transfer.idempotency_key != "f" * 64


def test_sql_injection_recipient_is_rejected_as_literal_input(
    app, client, user_factory, login_client
):
    sender = user_factory("alice")
    recipient = user_factory("bobby")
    login(client, login_client)

    response = submit_transfer(client, recipient="' OR 1=1 --")

    assert response.status_code == 400
    with app.app_context():
        assert wallet_balances(sender.id, recipient.id) == (100000, 100000)
        assert_empty_transfer_state()


def test_dormant_sender_old_session_cannot_transfer(
    app, client, user_factory, login_client
):
    sender = user_factory("alice", balance=500)
    recipient = user_factory("bobby", balance=500)
    login(client, login_client)
    csrf, token, _response = transfer_form_tokens(client)
    with app.app_context():
        stored = db.session.get(User, sender.id)
        stored.status = "dormant"
        stored.auth_version += 1
        db.session.commit()

    response = submit_transfer(
        client,
        csrf_token=csrf,
        idempotency_token=token,
    )

    assert response.status_code == 302
    with app.app_context():
        assert wallet_balances(sender.id, recipient.id) == (500, 500)
        assert_empty_transfer_state()


def test_transfer_minute_rate_limit_counts_invalid_posts(
    client, user_factory, login_client
):
    user_factory("alice")
    user_factory("bobby")
    login(client, login_client)
    csrf, token, _response = transfer_form_tokens(client)

    responses = [
        submit_transfer(
            client,
            amount="0",
            csrf_token=csrf,
            idempotency_token=token,
        )
        for _index in range(4)
    ]

    assert [response.status_code for response in responses[:3]] == [400, 400, 400]
    assert responses[3].status_code == 429


def test_wallet_get_rate_limit_is_shared_by_ip(client, user_factory, login_client):
    user_factory("alice")
    login(client, login_client)

    responses = [client.get("/wallet") for _index in range(61)]

    assert all(response.status_code == 200 for response in responses[:60])
    assert responses[60].status_code == 429
    assert responses[60].headers["Cache-Control"] == "no-store, private"


def test_transfer_hour_rate_limit_is_independent_of_minute_window(
    client, user_factory, login_client, monkeypatch
):
    user_factory("alice")
    user_factory("bobby")
    login(client, login_client)
    csrf, token, _response = transfer_form_tokens(client)
    clock = [time.time()]
    monkeypatch.setattr(memory_storage.time, "time", lambda: clock[0])

    for _index in range(10):
        response = submit_transfer(
            client,
            amount="0",
            csrf_token=csrf,
            idempotency_token=token,
        )
        assert response.status_code == 400
        clock[0] += 61

    response = submit_transfer(
        client,
        amount="0",
        csrf_token=csrf,
        idempotency_token=token,
    )
    assert response.status_code == 429


def test_same_token_same_payload_is_debited_and_audited_once(app, user_factory):
    sender = user_factory("alice", balance=1000)
    recipient = user_factory("bobby", balance=100)
    token = secrets.token_urlsafe(32)
    with app.app_context():
        first = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=200,
            current_password=PASSWORD,
            raw_idempotency_token=token,
        )
        second = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=200,
            current_password=PASSWORD,
            raw_idempotency_token=token,
        )

        assert first.result is TransferResult.CREATED
        assert second.result is TransferResult.IDEMPOTENT
        assert first.transfer_id == second.transfer_id
        assert wallet_balances(sender.id, recipient.id) == (800, 300)
        assert db.session.execute(db.select(Transfer.id)).all().__len__() == 1
        assert (
            db.session.execute(
                db.select(AuditLog.id).where(AuditLog.action == "transfer.created")
            )
            .all()
            .__len__()
            == 1
        )


def test_duplicate_route_returns_existing_detail_and_mismatch_is_409(
    app, client, user_factory, login_client
):
    sender = user_factory("alice", balance=1000)
    recipient = user_factory("bobby", balance=500)
    login(client, login_client)
    csrf, token, _response = transfer_form_tokens(client)

    first = submit_transfer(
        client,
        amount="100",
        csrf_token=csrf,
        idempotency_token=token,
    )
    duplicate = submit_transfer(
        client,
        amount="100",
        csrf_token=csrf,
        idempotency_token=token,
    )
    conflict = submit_transfer(
        client,
        amount="101",
        csrf_token=csrf,
        idempotency_token=token,
    )

    assert first.status_code == duplicate.status_code == 303
    assert first.location == duplicate.location
    assert conflict.status_code == 409
    assert token.encode() not in conflict.data
    with app.app_context():
        assert wallet_balances(sender.id, recipient.id) == (900, 600)
        assert db.session.execute(db.select(Transfer.id)).all().__len__() == 1
        assert db.session.execute(db.select(AuditLog.id)).all().__len__() == 1


@pytest.mark.parametrize("conflict_kind", ["amount", "recipient"])
def test_same_token_mismatched_payload_conflicts_without_state_change(
    app, user_factory, conflict_kind
):
    sender = user_factory("alice", balance=1000)
    first_recipient = user_factory("bobby", balance=100)
    other_recipient = user_factory("charlie", balance=100)
    token = secrets.token_urlsafe(32)
    with app.app_context():
        first = create_transfer(
            sender_id=sender.id,
            recipient_username=first_recipient.username,
            amount=200,
            current_password=PASSWORD,
            raw_idempotency_token=token,
        )
        before = wallet_balances(sender.id, first_recipient.id, other_recipient.id)
        second = create_transfer(
            sender_id=sender.id,
            recipient_username=(
                other_recipient.username
                if conflict_kind == "recipient"
                else first_recipient.username
            ),
            amount=201 if conflict_kind == "amount" else 200,
            current_password=PASSWORD,
            raw_idempotency_token=token,
        )

        assert first.result is TransferResult.CREATED
        assert second.result is TransferResult.IDEMPOTENCY_CONFLICT
        assert (
            wallet_balances(sender.id, first_recipient.id, other_recipient.id) == before
        )
        assert db.session.execute(db.select(Transfer.id)).all().__len__() == 1
        assert db.session.execute(db.select(AuditLog.id)).all().__len__() == 1


def test_same_raw_token_for_different_senders_has_separate_namespace(app, user_factory):
    first_sender = user_factory("alice", balance=500)
    second_sender = user_factory("bobby", balance=500)
    recipient = user_factory("charlie", balance=500)
    token = secrets.token_urlsafe(32)
    with app.app_context():
        outcomes = [
            create_transfer(
                sender_id=sender.id,
                recipient_username=recipient.username,
                amount=100,
                current_password=PASSWORD,
                raw_idempotency_token=token,
            )
            for sender in (first_sender, second_sender)
        ]
        assert [outcome.result for outcome in outcomes] == [
            TransferResult.CREATED,
            TransferResult.CREATED,
        ]
        assert wallet_balances(first_sender.id, second_sender.id, recipient.id) == (
            400,
            400,
            700,
        )
        keys = db.session.execute(
            db.select(Transfer.idempotency_key).order_by(Transfer.idempotency_key)
        ).scalars()
        assert sorted(keys) == sorted(
            (
                derive_idempotency_key(first_sender.id, token),
                derive_idempotency_key(second_sender.id, token),
            )
        )


def test_sender_wallet_missing_returns_database_error_without_rows(app, user_factory):
    sender = user_factory("alice")
    recipient = user_factory("bobby")
    with app.app_context():
        db.session.execute(db.delete(Wallet).where(Wallet.user_id == sender.id))
        db.session.commit()
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=100,
            current_password=PASSWORD,
            raw_idempotency_token=secrets.token_urlsafe(32),
        )
        assert outcome.result is TransferResult.DATABASE_ERROR
        assert wallet_balances(recipient.id) == (100000,)
        assert_empty_transfer_state()


def test_recipient_wallet_missing_rolls_back_everything(app, user_factory):
    sender = user_factory("alice", balance=500)
    recipient = user_factory("bobby", balance=500)
    with app.app_context():
        db.session.execute(db.delete(Wallet).where(Wallet.user_id == recipient.id))
        db.session.commit()
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=100,
            current_password=PASSWORD,
            raw_idempotency_token=secrets.token_urlsafe(32),
        )
        assert outcome.result is TransferResult.RECIPIENT_UNAVAILABLE
        assert wallet_balances(sender.id) == (500,)
        assert_empty_transfer_state()


def test_credit_rowcount_failure_rolls_back_actual_database_state(
    app, user_factory, monkeypatch
):
    sender = user_factory("alice", balance=500)
    recipient = user_factory("bobby", balance=500)
    with app.app_context():
        monkeypatch.setattr(wallet_services, "_credit_recipient", lambda *_args: 0)
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=100,
            current_password=PASSWORD,
            raw_idempotency_token=secrets.token_urlsafe(32),
        )
        assert outcome.result is TransferResult.RECIPIENT_UNAVAILABLE
        assert wallet_balances(sender.id, recipient.id) == (500, 500)
        assert_empty_transfer_state()


def test_audit_failure_rolls_back_actual_database_state(app, user_factory, monkeypatch):
    sender = user_factory("alice", balance=500)
    recipient = user_factory("bobby", balance=500)
    with app.app_context():
        monkeypatch.setattr(
            wallet_services,
            "add_audit_log",
            lambda **_kwargs: (_ for _ in ()).throw(ValueError("sensitive marker")),
        )
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=100,
            current_password=PASSWORD,
            raw_idempotency_token=secrets.token_urlsafe(32),
        )
        assert outcome.result is TransferResult.DATABASE_ERROR
        assert wallet_balances(sender.id, recipient.id) == (500, 500)
        assert_empty_transfer_state()


def test_commit_failure_rolls_back_actual_database_state(
    app, user_factory, monkeypatch
):
    sender = user_factory("alice", balance=500)
    recipient = user_factory("bobby", balance=500)
    with app.app_context():
        monkeypatch.setattr(
            db.session,
            "commit",
            lambda: (_ for _ in ()).throw(SQLAlchemyError("private commit marker")),
        )
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=100,
            current_password=PASSWORD,
            raw_idempotency_token=secrets.token_urlsafe(32),
        )
        assert outcome.result is TransferResult.DATABASE_ERROR
        assert wallet_balances(sender.id, recipient.id) == (500, 500)
        assert_empty_transfer_state()


def test_integrity_error_is_rolled_back_and_session_remains_usable(
    app, user_factory, monkeypatch
):
    sender = user_factory("alice", balance=500)
    recipient = user_factory("bobby", balance=500)
    with app.app_context():
        monkeypatch.setattr(
            db.session,
            "flush",
            lambda: (_ for _ in ()).throw(
                IntegrityError("insert", {}, RuntimeError("unique race"))
            ),
        )
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=100,
            current_password=PASSWORD,
            raw_idempotency_token=secrets.token_urlsafe(32),
        )
        assert outcome.result is TransferResult.DATABASE_ERROR
        assert wallet_balances(sender.id, recipient.id) == (500, 500)
        assert_empty_transfer_state()


def test_database_error_route_is_generic_and_keeps_token_hidden_only(
    client, user_factory, login_client, monkeypatch, caplog
):
    user_factory("alice")
    user_factory("bobby")
    login(client, login_client)
    csrf, token, _response = transfer_form_tokens(client)
    submitted_password = "private-password-marker"
    monkeypatch.setattr(
        wallet_routes,
        "create_transfer",
        lambda **_kwargs: TransferOutcome(TransferResult.DATABASE_ERROR),
    )

    response = submit_transfer(
        client,
        password=submitted_password,
        csrf_token=csrf,
        idempotency_token=token,
    )

    assert response.status_code == 500
    assert "요청을 처리하지 못했습니다" in response.get_data(as_text=True)
    assert named_input(response, "idempotency_token") == token
    assert response.data.count(token.encode()) == 1
    parser = VisibleTextParser()
    parser.feed(response.get_data(as_text=True))
    assert token not in "".join(parser.text)
    assert token not in caplog.text
    for secret in (submitted_password, "constraint", "traceback"):
        assert secret.lower().encode() not in response.data.lower()


def test_ambiguous_commit_preserves_token_and_retry_is_exactly_once(
    app, client, user_factory, login_client, monkeypatch, caplog
):
    sender = user_factory("alice", balance=500)
    recipient = user_factory("bobby", balance=0)
    login(client, login_client)
    csrf, token, _response = transfer_form_tokens(client)
    submitted_password = PASSWORD
    wallet_update_statements = []

    with app.app_context():
        engine = db.engine
        original_commit = db.session.commit
        commit_state = {"raised": False}

        def commit_then_raise():
            original_commit()
            if not commit_state["raised"]:
                commit_state["raised"] = True
                raise SQLAlchemyError("ambiguous private commit marker")

        def capture_wallet_updates(
            _connection,
            _cursor,
            statement,
            _parameters,
            _context,
            _executemany,
        ):
            if statement.lstrip().upper().startswith("UPDATE WALLETS"):
                wallet_update_statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture_wallet_updates)
        try:
            with monkeypatch.context() as patch:
                patch.setattr(db.session, "commit", commit_then_raise)
                first = submit_transfer(
                    client,
                    recipient=recipient.username,
                    amount="100",
                    password=submitted_password,
                    csrf_token=csrf,
                    idempotency_token=token,
                )

            assert first.status_code == 500
            assert "요청을 처리하지 못했습니다" in first.get_data(as_text=True)
            assert named_input(first, "idempotency_token") == token
            assert first.data.count(token.encode()) == 1
            first_parser = VisibleTextParser()
            first_parser.feed(first.get_data(as_text=True))
            assert token not in "".join(first_parser.text)
            assert token not in caplog.text
            assert submitted_password.encode() not in first.data
            assert b"constraint" not in first.data.lower()
            assert b"traceback" not in first.data.lower()

            transfer = db.session.execute(db.select(Transfer)).scalar_one()
            transfer_id = transfer.id
            audit = db.session.execute(
                db.select(AuditLog).where(AuditLog.action == "transfer.created")
            ).scalar_one()
            assert audit.target_id == transfer_id
            assert wallet_balances(sender.id, recipient.id) == (400, 100)

            retry_csrf = named_input(first, "csrf_token")
            second = submit_transfer(
                client,
                recipient=recipient.username,
                amount="100",
                password=submitted_password,
                csrf_token=retry_csrf,
                idempotency_token=token,
            )

            assert second.status_code == 303
            assert second.location.endswith(f"/wallet/transfers/{transfer_id}")
            assert token not in second.location
            assert submitted_password not in second.location
            assert db.session.execute(db.select(Transfer.id)).all() == [(transfer_id,)]
            assert (
                db.session.execute(
                    db.select(AuditLog.id).where(AuditLog.action == "transfer.created")
                )
                .all()
                .__len__()
                == 1
            )
            assert wallet_balances(sender.id, recipient.id) == (400, 100)
        finally:
            event.remove(engine, "before_cursor_execute", capture_wallet_updates)

    assert len(wallet_update_statements) == 2
    assert any("balance -" in statement for statement in wallet_update_statements)
    assert any("balance +" in statement for statement in wallet_update_statements)


@pytest.fixture
def file_sqlite_app(tmp_path):
    database_path = tmp_path / "wallet-concurrency.sqlite"
    application = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "PRODUCT_UPLOAD_DIR": str(tmp_path / "uploads"),
        },
    )
    limiter.reset()
    with application.app_context():
        db.create_all()
    yield application, database_path
    with application.app_context():
        db.session.remove()
        db.drop_all()
    limiter.reset()


def test_file_sqlite_database_mode_is_owner_only(file_sqlite_app):
    _application, database_path = file_sqlite_app

    assert database_path.is_file()
    assert not database_path.is_symlink()
    assert stat.S_IMODE(database_path.stat().st_mode) == 0o600


def seed_file_users(application, specifications):
    ids = {}
    with application.app_context():
        for username, balance in specifications:
            user = User(username=username, status="active", role="user")
            user.set_password(PASSWORD)
            db.session.add_all((user, Wallet(user=user, balance=balance)))
            db.session.flush()
            ids[username] = user.id
        db.session.commit()
    return ids


def concurrent_transfer_worker(
    application,
    barrier,
    *,
    sender_id,
    recipient_username,
    amount,
    token,
):
    with application.app_context():
        session_id = id(db.session())
        thread_id = threading.get_ident()
        barrier.wait(timeout=10)
        outcome = create_transfer(
            sender_id=sender_id,
            recipient_username=recipient_username,
            amount=amount,
            current_password=PASSWORD,
            raw_idempotency_token=token,
        )
        return outcome, session_id, thread_id


def test_concurrent_distinct_tokens_prevent_double_spend_on_file_sqlite(
    file_sqlite_app,
):
    application, database_path = file_sqlite_app
    assert Path(database_path).is_file()
    ids = seed_file_users(
        application,
        (("sender", 100), ("recipient1", 0), ("recipient2", 0)),
    )
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                concurrent_transfer_worker,
                application,
                barrier,
                sender_id=ids["sender"],
                recipient_username=f"recipient{index}",
                amount=80,
                token=secrets.token_urlsafe(32),
            )
            for index in (1, 2)
        ]
        results = [future.result(timeout=15) for future in futures]

    outcomes = [result[0].result for result in results]
    assert outcomes.count(TransferResult.CREATED) == 1
    assert outcomes.count(TransferResult.INSUFFICIENT_FUNDS) == 1
    assert len({result[1] for result in results}) == 2
    assert len({result[2] for result in results}) == 2
    with application.app_context():
        balances = wallet_balances(ids["sender"], ids["recipient1"], ids["recipient2"])
        transfer_count = db.session.execute(
            db.select(db.func.count()).select_from(Transfer)
        ).scalar_one()
        audit_count = db.session.execute(
            db.select(db.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "transfer.created")
        ).scalar_one()
        assert balances[0] >= 0
        assert balances[0] == 20
        assert sum(balances) == 100
        assert transfer_count == outcomes.count(TransferResult.CREATED) == 1
        assert audit_count == 1


def test_concurrent_same_token_is_exactly_once_on_file_sqlite(file_sqlite_app):
    application, database_path = file_sqlite_app
    assert Path(database_path).is_file()
    ids = seed_file_users(application, (("sender", 100), ("recipient", 0)))
    barrier = threading.Barrier(2)
    token = secrets.token_urlsafe(32)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                concurrent_transfer_worker,
                application,
                barrier,
                sender_id=ids["sender"],
                recipient_username="recipient",
                amount=80,
                token=token,
            )
            for _index in range(2)
        ]
        results = [future.result(timeout=15) for future in futures]

    outcomes = [result[0] for result in results]
    assert sorted(outcome.result.name for outcome in outcomes) == [
        "CREATED",
        "IDEMPOTENT",
    ]
    assert len({outcome.transfer_id for outcome in outcomes}) == 1
    assert len({result[1] for result in results}) == 2
    assert len({result[2] for result in results}) == 2
    with application.app_context():
        assert wallet_balances(ids["sender"], ids["recipient"]) == (20, 80)
        assert (
            db.session.execute(
                db.select(db.func.count()).select_from(Transfer)
            ).scalar_one()
            == 1
        )
        assert (
            db.session.execute(
                db.select(db.func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "transfer.created")
            ).scalar_one()
            == 1
        )


def test_history_filters_directions_sorts_and_excludes_other_users(app, user_factory):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    charlie = user_factory("charlie")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with app.app_context():
        sent_id = seed_transfer(
            alice.id, bobby.id, 10, created_at=base + timedelta(seconds=1)
        )
        received_id = seed_transfer(
            bobby.id, alice.id, 20, created_at=base + timedelta(seconds=2)
        )
        seed_transfer(bobby.id, charlie.id, 30, created_at=base + timedelta(seconds=3))

        all_page = list_transfer_history(
            user_id=alice.id,
            direction="all",
            sort="newest",
            page=1,
            per_page=20,
        )
        sent_page = list_transfer_history(
            user_id=alice.id,
            direction="sent",
            sort="oldest",
            page=1,
            per_page=20,
        )
        received_page = list_transfer_history(
            user_id=alice.id,
            direction="received",
            sort="oldest",
            page=1,
            per_page=20,
        )

        assert [item.id for item in all_page.items] == [received_id, sent_id]
        assert [
            (item.direction, item.counterpart_username) for item in all_page.items
        ] == [
            ("received", "bobby"),
            ("sent", "bobby"),
        ]
        assert [item.id for item in sent_page.items] == [sent_id]
        assert [item.id for item in received_page.items] == [received_id]


def test_wallet_history_uses_fixed_twenty_row_sql_pagination_and_preserves_filters(
    app, client, user_factory, login_client, monkeypatch
):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    with app.app_context():
        for amount in range(1, 22):
            seed_transfer(alice.id, bobby.id, amount)
    login(client, login_client)
    captured = {}
    original_render = wallet_routes.render_template

    def capture(template, **context):
        captured.update(context)
        return original_render(template, **context)

    monkeypatch.setattr(wallet_routes, "render_template", capture)
    response = client.get(
        "/wallet",
        query_string={
            "page": "1",
            "direction": "sent",
            "sort": "oldest",
            "per_page": "1",
            "unknown": "ignored",
        },
    )

    assert response.status_code == 200
    page = captured["page"]
    assert isinstance(page, TransferHistoryPage)
    assert page.per_page == 20
    assert len(page.items) == 20
    assert page.total == 21
    assert page.pages == 2
    assert page.has_next is True and page.next_num == 2
    assert captured["pagination_params"] == {
        "direction": "sent",
        "sort": "oldest",
    }
    assert "direction=sent" in response.get_data(as_text=True)
    assert "sort=oldest" in response.get_data(as_text=True)
    assert "per_page" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=1001",
        "page=not-an-integer",
        "direction=invalid",
        "sort=invalid",
    ],
)
def test_wallet_history_rejects_invalid_filter_values(
    client, user_factory, login_client, query
):
    user_factory("alice")
    login(client, login_client)
    response = client.get(f"/wallet?{query}")
    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "no-store, private"


def test_transfer_detail_allows_participants_and_hides_from_third_party(
    app, user_factory, login_client
):
    sender = user_factory("sender")
    recipient = user_factory("recipient")
    user_factory("thirduser")
    with app.app_context():
        transfer_id = seed_transfer(sender.id, recipient.id, 777)

    sender_client = app.test_client()
    recipient_client = app.test_client()
    third_client = app.test_client()
    login(sender_client, login_client, "sender")
    login(recipient_client, login_client, "recipient")
    login(third_client, login_client, "thirduser")

    sender_response = sender_client.get(f"/wallet/transfers/{transfer_id}")
    recipient_response = recipient_client.get(f"/wallet/transfers/{transfer_id}")
    forbidden = third_client.get(f"/wallet/transfers/{transfer_id}")
    missing = third_client.get(f"/wallet/transfers/{uuid4()}")
    assert sender_response.status_code == recipient_response.status_code == 200
    assert sender_response.headers["Cache-Control"] == "no-store, private"
    assert "보낸 송금" in sender_response.get_data(as_text=True)
    assert "받은 송금" in recipient_response.get_data(as_text=True)
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.data == missing.data


def test_wallet_dtos_have_only_allowlisted_fields():
    assert {field.name for field in fields(WalletSummaryView)} == {
        "username",
        "balance",
    }
    assert {field.name for field in fields(TransferHistoryView)} == {
        "id",
        "direction",
        "counterpart_username",
        "amount",
        "created_at",
    }
    assert {field.name for field in fields(TransferHistoryPage)} == {
        "items",
        "page",
        "per_page",
        "total",
        "pages",
        "has_prev",
        "has_next",
        "prev_num",
        "next_num",
    }
    assert {field.name for field in fields(TransferDetailView)} == {
        "id",
        "sender_username",
        "recipient_username",
        "direction",
        "amount",
        "created_at",
    }
    forbidden = {
        "sender_id",
        "recipient_id",
        "idempotency_key",
        "password_hash",
        "auth_version",
        "role",
        "session",
    }
    for dto in (
        WalletSummaryView,
        TransferHistoryView,
        TransferHistoryPage,
        TransferDetailView,
    ):
        assert forbidden.isdisjoint(field.name for field in fields(dto))


def test_history_and_detail_selects_never_project_idempotency_key(app, user_factory):
    sender = user_factory("sender")
    recipient = user_factory("recipient")
    statements = []
    with app.app_context():
        transfer_id = seed_transfer(sender.id, recipient.id, 100)
        engine = db.engine

        def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture)
        try:
            page = list_transfer_history(
                user_id=sender.id,
                direction="all",
                sort="newest",
                page=1,
                per_page=20,
            )
            detail = get_transfer_detail(
                user_id=sender.id,
                transfer_id=transfer_id,
            )
        finally:
            event.remove(engine, "before_cursor_execute", capture)

        assert page.items and detail is not None
        transfer_selects = [
            statement for statement in statements if "FROM transfers" in statement
        ]
        assert transfer_selects
        assert all("idempotency_key" not in statement for statement in transfer_selects)


def test_real_transfer_is_visible_to_admin_and_transfer_audit_filter(
    app, user_factory, login_client
):
    sender = user_factory("sender", balance=500)
    recipient = user_factory("recipient", balance=500)
    user_factory("administrator", role="admin")
    token = secrets.token_urlsafe(32)
    with app.app_context():
        outcome = create_transfer(
            sender_id=sender.id,
            recipient_username=recipient.username,
            amount=123,
            current_password=PASSWORD,
            raw_idempotency_token=token,
        )
        assert outcome.result is TransferResult.CREATED
        derived = derive_idempotency_key(sender.id, token)

    admin_client = app.test_client()
    login(admin_client, login_client, "administrator")
    transfers = admin_client.get("/admin/transfers?q=sender&sort=oldest")
    audits = admin_client.get(
        "/admin/audit-logs?target_type=transfer&q=transfer.created"
    )
    assert transfers.status_code == audits.status_code == 200
    assert "sender" in transfers.get_data(as_text=True)
    assert "recipient" in transfers.get_data(as_text=True)
    assert "123" in transfers.get_data(as_text=True)
    assert "transfer.created" in audits.get_data(as_text=True)
    assert "amount" in audits.get_data(as_text=True)
    for response in (transfers, audits):
        assert token.encode() not in response.data
        assert derived.encode() not in response.data
        assert sender.id.encode() not in response.data
        assert recipient.id.encode() not in response.data


def test_regular_user_cannot_access_admin_transfer_projection(
    client, user_factory, login_client
):
    user_factory("alice")
    login(client, login_client)
    assert client.get("/admin/transfers").status_code == 403


def test_transfer_routes_are_append_only_and_admin_is_get_only(app):
    rules = tuple(app.url_map.iter_rules())
    admin_rules = [rule for rule in rules if rule.rule == "/admin/transfers"]
    assert len(admin_rules) == 1
    assert admin_rules[0].methods == {"GET", "HEAD", "OPTIONS"}

    wallet_rules = [rule for rule in rules if rule.rule.startswith("/wallet")]
    assert {
        (rule.rule, frozenset(rule.methods - {"HEAD", "OPTIONS"}))
        for rule in wallet_rules
    } == {
        ("/wallet", frozenset({"GET"})),
        ("/wallet/transfer", frozenset({"GET"})),
        ("/wallet/transfer", frozenset({"POST"})),
        ("/wallet/transfers/<uuid:transfer_id>", frozenset({"GET"})),
    }
    mutation_methods = {"PUT", "PATCH", "DELETE"}
    assert not [
        rule
        for rule in rules
        if "transfer" in rule.rule.lower()
        and mutation_methods.intersection(rule.methods)
    ]
    assert [
        rule.endpoint
        for rule in rules
        if "transfer" in rule.rule.lower() and "POST" in rule.methods
    ] == ["wallet.transfer_submit"]


def test_wallet_templates_have_no_inline_code_safe_filter_or_sensitive_labels():
    template_root = Path("app/templates/wallet")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(template_root.glob("*.html"))
    )
    assert "<script" not in source.lower()
    assert "<style" not in source.lower()
    assert "|safe" not in source
    assert "Markup" not in source
    assert "idempotency_key" not in source
    assert "sender_id" not in source
    assert "recipient_id" not in source
    assert 'autocomplete="current-password"' in source
    assert 'autocomplete="username"' in source
    assert "min=1" in source
    assert "max=1000000000" in source
    assert "step=1" in source


def test_in_memory_sqlite_keeps_foreign_keys_busy_timeout_and_defaults(app):
    secure_sqlite_database_file("file:shared-memory?mode=memory&cache=shared")
    with app.app_context():
        assert db.session.execute(db.text("SELECT 1")).scalar_one() == 1
        foreign_keys = db.session.execute(db.text("PRAGMA foreign_keys")).scalar_one()
        busy_timeout = db.session.execute(db.text("PRAGMA busy_timeout")).scalar_one()
        database_list = db.session.execute(db.text("PRAGMA database_list")).all()

    assert foreign_keys == 1
    assert busy_timeout == 5000
    assert next(row[2] for row in database_list if row[1] == "main") == ""
    assert app.config["TRANSFER_MIN_AMOUNT"] == 1
    assert app.config["TRANSFER_MAX_AMOUNT"] == 1_000_000_000
    assert app.config["TRANSFER_HISTORY_PER_PAGE"] == 20
    assert app.config["TRANSFER_PAGE_MAX"] == 1000
    assert app.config["TRANSFER_IDEMPOTENCY_TOKEN_BYTES"] == 32


def test_instance_directory_mode_is_owner_only(app):
    instance_path = Path(app.instance_path)

    assert instance_path.is_dir()
    assert not instance_path.is_symlink()
    assert stat.S_IMODE(instance_path.stat().st_mode) == 0o700


def test_instance_directory_rejects_symlink_and_non_directory(tmp_path):
    target = tmp_path / "target"
    target.mkdir(mode=0o755)
    symlink = tmp_path / "instance-link"
    symlink.symlink_to(target, target_is_directory=True)
    non_directory = tmp_path / "instance-file"
    non_directory.write_text("not a directory", encoding="utf-8")

    with pytest.raises(RuntimeError, match="must not be a symbolic link"):
        secure_instance_directory(str(symlink))
    with pytest.raises(RuntimeError, match="must be a directory"):
        secure_instance_directory(str(non_directory))

    assert symlink.is_symlink()
    assert stat.S_IMODE(target.stat().st_mode) == 0o755


def test_sqlite_database_permission_helper_rejects_symlink(tmp_path):
    target = tmp_path / "target.sqlite"
    target.write_bytes(b"not a database")
    target.chmod(0o644)
    symlink = tmp_path / "database.sqlite"
    symlink.symlink_to(target)

    with pytest.raises(RuntimeError, match="must not be a symbolic link"):
        secure_sqlite_database_file(str(symlink))

    assert symlink.is_symlink()
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_instance_database_and_upload_artifacts_are_not_git_tracked():
    tracked = (
        subprocess.run(
            ["git", "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .split("\0")
    )

    for relative_path in filter(None, tracked):
        path = Path(relative_path)
        assert "instance" not in path.parts
        assert "uploads" not in path.parts
        assert path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}


def test_github_actions_ci_contains_required_non_optional_checks():
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    required_fragments = (
        "push:",
        "pull_request:",
        "actions/checkout@v4",
        "fetch-depth: 0",
        "persist-credentials: false",
        "git show-ref",
        "phase-01-foundation",
        "phase-02-auth-users",
        "phase-03-products-search",
        "phase-04-chat",
        "phase-05-moderation-admin",
        "actions/setup-python@",
        'python-version: "3.12"',
        "requirements-dev.txt",
        "python -m pytest",
        "--cov-fail-under=90",
        "python -m ruff check .",
        "python -m ruff format --check .",
        "python -m bandit -q -r app scripts run.py",
        "pip-audit -r requirements.txt",
        "pip-audit -r requirements-dev.txt",
        "python -m pip check",
        "python -m compileall -q app scripts tests run.py",
        "python -m flask --app run.py db upgrade",
        "python -m flask --app run.py db check",
        "secrets.token_urlsafe(48)",
    )
    assert all(fragment in source for fragment in required_fragments)
    assert "continue-on-error" not in source
    assert "${{ secrets." not in source

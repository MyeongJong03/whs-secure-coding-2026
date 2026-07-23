import re
import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.chat.rate_limit import ChatEventLimiter
from app.extensions import db, socketio
from app.models import ChatMessage, DirectConversation, User


def login(app, login_client, username="alice"):
    client = app.test_client()
    assert login_client(client, username=username).status_code == 303
    return client


def page_csrf(client, path="/chat") -> str:
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(rb'data-chat-csrf="([^"]+)"', response.data)
    assert match is not None
    return match.group(1).decode()


def form_csrf(client, path="/me") -> str:
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
    assert match is not None
    return match.group(1).decode()


def connect_socket(app, client, *, token=None):
    if token is None:
        token = page_csrf(client)
    return socketio.test_client(
        app,
        flask_test_client=client,
        namespace="/chat",
        auth={"csrf_token": token},
    )


def create_conversation(app, first, second) -> str:
    with app.app_context():
        user1_id, user2_id = sorted((first.id, second.id))
        conversation = DirectConversation(user1_id=user1_id, user2_id=user2_id)
        db.session.add(conversation)
        db.session.commit()
        return conversation.id


def disconnect_all(*clients) -> None:
    for client in clients:
        if client.is_connected("/chat"):
            client.disconnect(namespace="/chat")


def chat_messages(client) -> list[dict]:
    return [
        packet["args"][0]
        for packet in client.get_received("/chat")
        if packet["name"] == "chat:message"
    ]


def test_socket_connect_rejects_unauthenticated_even_with_valid_csrf(app, client):
    response = client.get("/auth/login")
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
    token = match.group(1).decode()

    chat_socket = connect_socket(app, client, token=token)

    assert not chat_socket.is_connected("/chat")


@pytest.mark.parametrize(
    "auth",
    [
        None,
        {},
        {"csrf_token": None},
        {"csrf_token": "invalid"},
        {"csrf_token": "invalid", "username": "alice"},
    ],
)
def test_socket_connect_rejects_missing_invalid_or_extra_auth(
    app, user_factory, login_client, auth
):
    user_factory()
    client = login(app, login_client)

    chat_socket = socketio.test_client(
        app,
        flask_test_client=client,
        namespace="/chat",
        auth=auth,
    )

    assert not chat_socket.is_connected("/chat")


def test_socket_connect_rejects_csrf_from_another_flask_session(
    app, user_factory, login_client
):
    user_factory("alice")
    user_factory("bobby")
    alice_client = login(app, login_client, "alice")
    bobby_client = login(app, login_client, "bobby")
    alice_token = page_csrf(alice_client)

    chat_socket = connect_socket(app, bobby_client, token=alice_token)

    assert not chat_socket.is_connected("/chat")


def test_valid_connect_registers_and_disconnect_removes_record(
    app, user_factory, login_client
):
    alice = user_factory()
    client = login(app, login_client)
    token = page_csrf(client)
    with client.session_transaction() as flask_session:
        before = dict(flask_session)

    chat_socket = connect_socket(app, client, token=token)

    assert chat_socket.is_connected("/chat")
    registry = app.extensions["chat_connection_registry"]
    assert registry.user_connection_count(alice.id) == 1
    with client.session_transaction() as flask_session:
        assert dict(flask_session) == before
    chat_socket.disconnect(namespace="/chat")
    assert registry.user_connection_count(alice.id) == 0


@pytest.mark.parametrize("change", ["dormant", "version"])
def test_socket_connect_rejects_stale_database_identity(
    app, user_factory, login_client, change
):
    alice = user_factory()
    client = login(app, login_client)
    token = page_csrf(client)
    with app.app_context():
        stored = db.session.get(User, alice.id)
        if change == "dormant":
            stored.status = "dormant"
        else:
            stored.auth_version += 1
        db.session.commit()

    chat_socket = connect_socket(app, client, token=token)

    assert not chat_socket.is_connected("/chat")


def test_socket_connection_cap_allows_five_and_rejects_sixth(
    app, user_factory, login_client
):
    user_factory()
    client = login(app, login_client)
    token = page_csrf(client)

    clients = [connect_socket(app, client, token=token) for _ in range(6)]

    assert [chat_socket.is_connected("/chat") for chat_socket in clients] == [
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    disconnect_all(*clients)


def test_registry_and_event_limiter_are_isolated_between_app_instances(app):
    from app import create_app

    other = create_app("testing")

    assert (
        app.extensions["chat_connection_registry"]
        is not other.extensions["chat_connection_registry"]
    )
    assert (
        app.extensions["chat_event_limiter"]
        is not other.extensions["chat_event_limiter"]
    )


def test_global_join_and_message_use_server_sender_and_room_scope(
    app, user_factory, login_client
):
    alice = user_factory("alice")
    user_factory("bobby")
    user_factory("carol")
    alice_http = login(app, login_client, "alice")
    bobby_http = login(app, login_client, "bobby")
    carol_http = login(app, login_client, "carol")
    alice_socket = connect_socket(app, alice_http)
    bobby_socket = connect_socket(app, bobby_http)
    carol_socket = connect_socket(app, carol_http)

    assert alice_socket.emit(
        "chat:send_global",
        {"body": "not joined"},
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "not_joined"}
    assert alice_socket.emit(
        "chat:join_global", {}, namespace="/chat", callback=True
    ) == {"ok": True}
    assert bobby_socket.emit("chat:join_global", namespace="/chat", callback=True) == {
        "ok": True
    }
    assert alice_socket.emit(
        "chat:send_global",
        {"body": "spoof", "sender_id": str(uuid.uuid4()), "username": "bobby"},
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "invalid_payload"}

    ack = alice_socket.emit(
        "chat:send_global",
        {"body": "hello"},
        namespace="/chat",
        callback=True,
    )

    assert ack == {"ok": True}
    alice_messages = chat_messages(alice_socket)
    bobby_messages = chat_messages(bobby_socket)
    assert len(alice_messages) == len(bobby_messages) == 1
    assert alice_messages == bobby_messages
    assert chat_messages(carol_socket) == []
    assert alice_messages[0]["scope"] == "global"
    assert set(alice_messages[0]) == {"scope", "message"}
    assert set(alice_messages[0]["message"]) == {
        "id",
        "sender_username",
        "body",
        "created_at_iso",
    }
    assert alice_messages[0]["message"]["sender_username"] == "alice"
    with app.app_context():
        stored = db.session.execute(db.select(ChatMessage)).scalar_one()
        assert stored.sender_id == alice.id
        assert stored.conversation_id is None
        assert stored.is_hidden is False
    disconnect_all(alice_socket, bobby_socket, carol_socket)


@pytest.mark.parametrize(
    "payload",
    [
        "not-a-dict",
        {},
        {"body": "hello", "extra": True},
        {"body": ""},
        {"body": " \r\n\t "},
        {"body": "a" * 501},
        {"body": "😀" * 501},
        {"body": "bad\x00body"},
        {"body": "bad\x01body"},
        {"body": "bad\x7fbody"},
        {"body": 123},
        {"body": "hello", "is_hidden": True},
    ],
)
def test_global_message_payload_validation(app, user_factory, login_client, payload):
    user_factory()
    app.extensions["chat_event_limiter"] = ChatEventLimiter(
        clock=None,
        message_burst_limit=50,
        message_burst_window=10,
        message_hourly_limit=100,
        join_limit=30,
        join_window=60,
    )
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)

    ack = chat_socket.emit(
        "chat:send_global", payload, namespace="/chat", callback=True
    )

    assert ack == {"ok": False, "code": "invalid_payload"}
    with app.app_context():
        assert (
            db.session.execute(db.select(ChatMessage.id)).scalar_one_or_none() is None
        )
    assert chat_messages(chat_socket) == []
    disconnect_all(chat_socket)


def test_message_normalizes_crlf_carriage_return_and_nfc(
    app, user_factory, login_client
):
    user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)

    ack = chat_socket.emit(
        "chat:send_global",
        {"body": " e\u0301\r\nline\rnext "},
        namespace="/chat",
        callback=True,
    )

    assert ack == {"ok": True}
    with app.app_context():
        body = db.session.execute(db.select(ChatMessage.body)).scalar_one()
    assert body == "é\nline\nnext"
    disconnect_all(chat_socket)


def test_message_utf8_byte_limit_is_configurable_and_exact_2000_bytes_allowed(
    app, user_factory, login_client
):
    user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)

    assert chat_socket.emit(
        "chat:send_global",
        {"body": "😀" * 500},
        namespace="/chat",
        callback=True,
    ) == {"ok": True}
    app.config["CHAT_MESSAGE_MAX_BYTES"] = 3
    assert chat_socket.emit(
        "chat:send_global",
        {"body": "éé"},
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "invalid_payload"}
    disconnect_all(chat_socket)


def test_global_commit_failure_rolls_back_and_does_not_broadcast(
    app, user_factory, login_client, monkeypatch
):
    user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)

    def fail_commit():
        raise SQLAlchemyError("private constraint body token")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    ack = chat_socket.emit(
        "chat:send_global",
        {"body": "must not emit"},
        namespace="/chat",
        callback=True,
    )

    assert ack == {"ok": False, "code": "server_error"}
    assert chat_messages(chat_socket) == []
    with app.app_context():
        assert (
            db.session.execute(db.select(ChatMessage.id)).scalar_one_or_none() is None
        )
    disconnect_all(chat_socket)


def test_message_burst_limit_is_shared_across_user_sockets(
    app, user_factory, login_client
):
    user_factory()
    http_client = login(app, login_client)
    first = connect_socket(app, http_client)
    second = connect_socket(app, http_client)
    for chat_socket in (first, second):
        assert chat_socket.emit(
            "chat:join_global", {}, namespace="/chat", callback=True
        ) == {"ok": True}

    acks = [
        (first if index % 2 == 0 else second).emit(
            "chat:send_global",
            {"body": f"message-{index}"},
            namespace="/chat",
            callback=True,
        )
        for index in range(6)
    ]

    assert all(ack == {"ok": True} for ack in acks[:5])
    assert acks[5] == {"ok": False, "code": "rate_limited"}
    with app.app_context():
        assert (
            db.session.execute(
                db.select(db.func.count()).select_from(ChatMessage)
            ).scalar_one()
            == 5
        )
    disconnect_all(first, second)


def test_message_hourly_limit_with_injected_clock(app, user_factory, login_client):
    clock = [100.0]
    app.extensions["chat_event_limiter"] = ChatEventLimiter(
        clock=lambda: clock[0],
        message_burst_limit=10,
        message_burst_window=1,
        message_hourly_limit=3,
        join_limit=30,
        join_window=60,
    )
    user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)

    acks = []
    for index in range(4):
        clock[0] += 2
        acks.append(
            chat_socket.emit(
                "chat:send_global",
                {"body": f"hourly-{index}"},
                namespace="/chat",
                callback=True,
            )
        )

    assert all(ack == {"ok": True} for ack in acks[:3])
    assert acks[3] == {"ok": False, "code": "rate_limited"}
    disconnect_all(chat_socket)


def test_malformed_message_attempts_consume_quota(app, user_factory, login_client):
    user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)

    for _ in range(5):
        assert chat_socket.emit(
            "chat:send_global", {}, namespace="/chat", callback=True
        ) == {"ok": False, "code": "invalid_payload"}

    assert chat_socket.emit(
        "chat:send_global",
        {"body": "valid but rate limited"},
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "rate_limited"}
    disconnect_all(chat_socket)


def test_join_rate_limit_and_malformed_join(app, user_factory, login_client):
    app.extensions["chat_event_limiter"] = ChatEventLimiter(
        clock=None,
        message_burst_limit=5,
        message_burst_window=10,
        message_hourly_limit=120,
        join_limit=2,
        join_window=60,
    )
    user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)

    assert chat_socket.emit(
        "chat:join_global",
        {"room": "arbitrary"},
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "invalid_payload"}
    assert chat_socket.emit(
        "chat:join_global", {}, namespace="/chat", callback=True
    ) == {"ok": True}
    assert chat_socket.emit(
        "chat:join_global", {}, namespace="/chat", callback=True
    ) == {"ok": False, "code": "rate_limited"}
    disconnect_all(chat_socket)


def test_rate_limiter_prunes_expired_message_and_join_timestamps():
    clock = [0.0]
    limiter = ChatEventLimiter(
        clock=lambda: clock[0],
        message_burst_limit=1,
        message_burst_window=10,
        message_hourly_limit=1,
        join_limit=1,
        join_window=10,
    )
    assert limiter.consume_message("user") is True
    assert limiter.consume_join("user") is True
    assert limiter.consume_message("user") is False
    assert limiter.consume_join("user") is False

    clock[0] = 3601

    assert limiter.consume_message("user") is True
    assert limiter.consume_join("user") is True


def test_direct_room_authorization_delivery_and_persistence(
    app, user_factory, login_client
):
    alice = user_factory("alice")
    user_factory("bobby")
    user_factory("carol")
    with app.app_context():
        bobby = db.session.execute(
            db.select(User).where(User.username == "bobby")
        ).scalar_one()
        conversation_id = create_conversation(app, alice, bobby)
    alice_http = login(app, login_client, "alice")
    bobby_http = login(app, login_client, "bobby")
    carol_http = login(app, login_client, "carol")
    alice_socket = connect_socket(app, alice_http)
    bobby_socket = connect_socket(app, bobby_http)
    carol_socket = connect_socket(app, carol_http)
    carol_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)

    join_payload = {"conversation_id": conversation_id}
    assert alice_socket.emit(
        "chat:join_direct", join_payload, namespace="/chat", callback=True
    ) == {"ok": True}
    assert bobby_socket.emit(
        "chat:join_direct", join_payload, namespace="/chat", callback=True
    ) == {"ok": True}
    assert carol_socket.emit(
        "chat:join_direct", join_payload, namespace="/chat", callback=True
    ) == {"ok": False, "code": "not_found"}

    ack = alice_socket.emit(
        "chat:send_direct",
        {"conversation_id": conversation_id, "body": "private"},
        namespace="/chat",
        callback=True,
    )

    assert ack == {"ok": True}
    alice_messages = chat_messages(alice_socket)
    assert alice_messages == chat_messages(bobby_socket)
    assert chat_messages(carol_socket) == []
    assert alice_messages[0]["scope"] == "direct"
    assert alice_messages[0]["conversation_id"] == conversation_id
    assert "room" not in alice_messages[0]
    with app.app_context():
        stored = db.session.execute(db.select(ChatMessage)).scalar_one()
        assert stored.conversation_id == conversation_id
        assert stored.sender_id == alice.id
    disconnect_all(alice_socket, bobby_socket, carol_socket)


@pytest.mark.parametrize(
    ("event", "payload", "code"),
    [
        ("chat:join_direct", {"conversation_id": "not-a-uuid"}, "invalid_payload"),
        (
            "chat:join_direct",
            {"conversation_id": str(uuid.uuid4()), "room": "chat:global"},
            "invalid_payload",
        ),
        ("chat:join_direct", {}, "invalid_payload"),
        (
            "chat:join_direct",
            {"conversation_id": str(uuid.uuid4())},
            "not_found",
        ),
        (
            "chat:send_direct",
            {"conversation_id": str(uuid.uuid4()), "body": "not joined"},
            "not_joined",
        ),
    ],
)
def test_direct_event_rejects_invalid_missing_or_arbitrary_scope(
    app, user_factory, login_client, event, payload, code
):
    user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)

    ack = chat_socket.emit(event, payload, namespace="/chat", callback=True)

    assert ack == {"ok": False, "code": code}
    disconnect_all(chat_socket)


def test_direct_send_rechecks_conversation_and_rejects_spoof_extra_fields(
    app, user_factory, login_client
):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    carol = user_factory("carol")
    first_id = create_conversation(app, alice, bobby)
    second_id = create_conversation(app, alice, carol)
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit(
        "chat:join_direct",
        {"conversation_id": first_id},
        namespace="/chat",
        callback=True,
    )

    assert chat_socket.emit(
        "chat:send_direct",
        {"conversation_id": second_id, "body": "wrong conversation"},
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "not_joined"}
    assert chat_socket.emit(
        "chat:send_direct",
        {
            "conversation_id": first_id,
            "body": "spoof",
            "sender_id": bobby.id,
        },
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "invalid_payload"}
    disconnect_all(chat_socket)


def test_direct_event_rate_limit_invalid_body_and_deleted_conversation_recheck(
    app, user_factory, login_client
):
    app.extensions["chat_event_limiter"] = ChatEventLimiter(
        clock=None,
        message_burst_limit=2,
        message_burst_window=10,
        message_hourly_limit=120,
        join_limit=1,
        join_window=60,
    )
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    conversation_id = create_conversation(app, alice, bobby)
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    join_payload = {"conversation_id": conversation_id}
    assert chat_socket.emit(
        "chat:join_direct", join_payload, namespace="/chat", callback=True
    ) == {"ok": True}
    assert chat_socket.emit(
        "chat:join_direct", join_payload, namespace="/chat", callback=True
    ) == {"ok": False, "code": "rate_limited"}
    assert chat_socket.emit(
        "chat:send_direct",
        {"conversation_id": conversation_id, "body": ""},
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "invalid_payload"}
    with app.app_context():
        conversation = db.session.get(DirectConversation, conversation_id)
        db.session.delete(conversation)
        db.session.commit()
    assert chat_socket.emit(
        "chat:send_direct",
        {"conversation_id": conversation_id, "body": "gone"},
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "not_found"}
    assert chat_socket.emit(
        "chat:send_direct",
        {"conversation_id": conversation_id, "body": "limited"},
        namespace="/chat",
        callback=True,
    ) == {"ok": False, "code": "rate_limited"}
    disconnect_all(chat_socket)


def test_direct_send_rejects_dormant_counterpart(app, user_factory, login_client):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    conversation_id = create_conversation(app, alice, bobby)
    alice_http = login(app, login_client, "alice")
    bobby_http = login(app, login_client, "bobby")
    alice_socket = connect_socket(app, alice_http)
    bobby_socket = connect_socket(app, bobby_http)
    for chat_socket in (alice_socket, bobby_socket):
        chat_socket.emit(
            "chat:join_direct",
            {"conversation_id": conversation_id},
            namespace="/chat",
            callback=True,
        )
    with app.app_context():
        stored = db.session.get(User, bobby.id)
        stored.status = "dormant"
        db.session.commit()

    ack = alice_socket.emit(
        "chat:send_direct",
        {"conversation_id": conversation_id, "body": "unavailable"},
        namespace="/chat",
        callback=True,
    )

    assert ack == {"ok": False, "code": "unavailable"}
    assert not bobby_socket.is_connected("/chat")
    with app.app_context():
        assert (
            db.session.execute(db.select(ChatMessage.id)).scalar_one_or_none() is None
        )
    disconnect_all(alice_socket, bobby_socket)


def test_direct_commit_failure_is_not_broadcast(
    app, user_factory, login_client, monkeypatch
):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    conversation_id = create_conversation(app, alice, bobby)
    alice_http = login(app, login_client, "alice")
    bobby_http = login(app, login_client, "bobby")
    alice_socket = connect_socket(app, alice_http)
    bobby_socket = connect_socket(app, bobby_http)
    for chat_socket in (alice_socket, bobby_socket):
        chat_socket.emit(
            "chat:join_direct",
            {"conversation_id": conversation_id},
            namespace="/chat",
            callback=True,
        )

    def fail_commit():
        raise SQLAlchemyError("private direct constraint")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    ack = alice_socket.emit(
        "chat:send_direct",
        {"conversation_id": conversation_id, "body": "must not emit"},
        namespace="/chat",
        callback=True,
    )

    assert ack == {"ok": False, "code": "server_error"}
    assert chat_messages(alice_socket) == []
    assert chat_messages(bobby_socket) == []
    disconnect_all(alice_socket, bobby_socket)


def test_socket_error_handler_emits_only_generic_error_and_redacted_log(
    app, user_factory, login_client, monkeypatch, caplog
):
    user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)

    def fail_validation(_body):
        raise RuntimeError("private body csrf_token constraint traceback")

    monkeypatch.setattr("app.chat.events.normalize_message_body", fail_validation)
    chat_socket.emit(
        "chat:send_global",
        {"body": "private-message-body"},
        namespace="/chat",
        callback=True,
    )
    packets = chat_socket.get_received("/chat")

    assert packets == [
        {
            "name": "chat:error",
            "args": [{"ok": False, "code": "server_error"}],
            "namespace": "/chat",
        }
    ]
    log_text = caplog.text
    assert "Unhandled chat event error: chat:send_global" in log_text
    for secret in (
        "private-message-body",
        "private body",
        "csrf_token",
        "constraint",
        "traceback",
    ):
        assert secret not in log_text
    disconnect_all(chat_socket)


def test_http_logout_disconnects_socket_and_prevents_later_receive(
    app, user_factory, login_client
):
    user_factory("alice")
    user_factory("bobby")
    alice_http = login(app, login_client, "alice")
    bobby_http = login(app, login_client, "bobby")
    alice_socket = connect_socket(app, alice_http)
    bobby_socket = connect_socket(app, bobby_http)
    for chat_socket in (alice_socket, bobby_socket):
        chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)
    token = form_csrf(alice_http)

    response = alice_http.post("/auth/logout", data={"csrf_token": token})

    assert response.status_code == 303
    assert not alice_socket.is_connected("/chat")
    assert bobby_socket.emit(
        "chat:send_global",
        {"body": "after logout"},
        namespace="/chat",
        callback=True,
    ) == {"ok": True}
    assert not alice_socket.is_connected("/chat")
    disconnect_all(alice_socket, bobby_socket)


def test_password_change_disconnects_old_socket_and_allows_new_session_socket(
    app, user_factory, login_client
):
    user_factory()
    http_client = login(app, login_client)
    old_socket = connect_socket(app, http_client)
    token = form_csrf(http_client)

    response = http_client.post(
        "/me/password",
        data={
            "current_password": "valid-test-password-123",
            "new_password": "new-valid-password-456",
            "new_password_confirm": "new-valid-password-456",
            "csrf_token": token,
        },
    )

    assert response.status_code == 303
    assert not old_socket.is_connected("/chat")
    new_socket = connect_socket(app, http_client)
    assert new_socket.is_connected("/chat")
    disconnect_all(old_socket, new_socket)


def test_auth_version_change_invalidates_old_socket_on_next_event(
    app, user_factory, login_client
):
    alice = user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)
    with app.app_context():
        stored = db.session.get(User, alice.id)
        stored.auth_version += 1
        db.session.commit()

    chat_socket.emit(
        "chat:send_global",
        {"body": "stale"},
        namespace="/chat",
        callback=True,
    )

    assert not chat_socket.is_connected("/chat")
    with app.app_context():
        assert (
            db.session.execute(db.select(ChatMessage.id)).scalar_one_or_none() is None
        )


def test_dormant_socket_is_pruned_before_broadcast_and_never_revives(
    app, user_factory, login_client
):
    alice = user_factory("alice")
    user_factory("bobby")
    alice_http = login(app, login_client, "alice")
    bobby_http = login(app, login_client, "bobby")
    alice_socket = connect_socket(app, alice_http)
    bobby_socket = connect_socket(app, bobby_http)
    for chat_socket in (alice_socket, bobby_socket):
        chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)
    with app.app_context():
        stored = db.session.get(User, alice.id)
        stored.status = "dormant"
        db.session.commit()

    assert bobby_socket.emit(
        "chat:send_global",
        {"body": "prune dormant"},
        namespace="/chat",
        callback=True,
    ) == {"ok": True}
    assert not alice_socket.is_connected("/chat")
    with app.app_context():
        stored = db.session.get(User, alice.id)
        stored.status = "active"
        db.session.commit()
    assert bobby_socket.emit(
        "chat:send_global",
        {"body": "still gone"},
        namespace="/chat",
        callback=True,
    ) == {"ok": True}
    assert not alice_socket.is_connected("/chat")
    disconnect_all(alice_socket, bobby_socket)


def test_max_age_socket_is_removed_before_event(app, user_factory, login_client):
    clock = [0.0]
    registry = app.extensions["chat_connection_registry"]
    registry._clock = lambda: clock[0]
    user_factory()
    http_client = login(app, login_client)
    chat_socket = connect_socket(app, http_client)
    chat_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)
    clock[0] = app.config["CHAT_SOCKET_MAX_AGE_SECONDS"] + 0.1

    chat_socket.emit(
        "chat:send_global",
        {"body": "too old"},
        namespace="/chat",
        callback=True,
    )

    assert not chat_socket.is_connected("/chat")
    with app.app_context():
        assert (
            db.session.execute(db.select(ChatMessage.id)).scalar_one_or_none() is None
        )


def test_max_age_socket_is_removed_before_another_users_broadcast(
    app, user_factory, login_client
):
    clock = [0.0]
    registry = app.extensions["chat_connection_registry"]
    registry._clock = lambda: clock[0]
    user_factory("alice")
    user_factory("bobby")
    alice_http = login(app, login_client, "alice")
    alice_socket = connect_socket(app, alice_http)
    alice_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)
    clock[0] = 100.0
    bobby_http = login(app, login_client, "bobby")
    bobby_socket = connect_socket(app, bobby_http)
    bobby_socket.emit("chat:join_global", {}, namespace="/chat", callback=True)
    clock[0] = app.config["CHAT_SOCKET_MAX_AGE_SECONDS"] + 0.1

    assert bobby_socket.emit(
        "chat:send_global",
        {"body": "fresh sender"},
        namespace="/chat",
        callback=True,
    ) == {"ok": True}
    assert not alice_socket.is_connected("/chat")
    assert bobby_socket.is_connected("/chat")
    disconnect_all(alice_socket, bobby_socket)

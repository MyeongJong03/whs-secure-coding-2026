import re
import uuid
from dataclasses import FrozenInstanceError, fields
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.chat.services import (
    DirectConversationResult,
    get_direct_conversation,
    get_message_history,
    list_direct_conversations,
    start_direct_conversation,
)
from app.chat.views import (
    ChatMessagePage,
    ChatMessageView,
    DirectConversationPage,
    DirectConversationSummary,
    DirectConversationView,
)
from app.extensions import db
from app.models import ChatMessage, DirectConversation, User, utc_now


def create_conversation(app, first, second) -> DirectConversation:
    with app.app_context():
        user1_id, user2_id = sorted((first.id, second.id))
        conversation = DirectConversation(user1_id=user1_id, user2_id=user2_id)
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id
    with app.app_context():
        return db.session.get(DirectConversation, conversation_id)


def seed_message(
    app,
    sender,
    body,
    *,
    conversation=None,
    hidden=False,
    created_at=None,
) -> str:
    with app.app_context():
        message = ChatMessage(
            sender_id=sender.id,
            conversation_id=conversation.id if conversation else None,
            body=body,
            is_hidden=hidden,
            created_at=created_at or utc_now(),
        )
        db.session.add(message)
        db.session.commit()
        return message.id


def start_token(client) -> str:
    response = client.get("/chat/direct")
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
    assert match is not None
    return match.group(1).decode()


@pytest.mark.parametrize(
    "path",
    ["/chat", "/chat/direct", f"/chat/direct/{uuid.uuid4()}"],
)
def test_chat_pages_require_authentication(client, path):
    response = client.get(path)

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_authenticated_global_chat_is_private_and_live_on_page_one(
    client, user_factory, login_client
):
    user_factory()
    assert login_client(client).status_code == 303

    response = client.get("/chat")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"
    assert b'data-chat-mode="global"' in response.data
    assert b'data-live-enabled="true"' in response.data
    assert b"socket.io-4.8.3.min.js" in response.data
    assert (
        b'integrity="sha384-kzavj5fiMwLKzzD1f8S7TeoVIEi7uKHvbTA3ueZkrzYq75pNQUiUi6Dy98Q3fxb0"'
        in response.data
    )


def test_chat_page_max_uses_injected_config(app, client, user_factory, login_client):
    user_factory()
    login_client(client)
    app.config["CHAT_PAGE_MAX"] = 2

    assert client.get("/chat?page=2").status_code == 200
    assert client.get("/chat?page=3").status_code == 400


@pytest.mark.parametrize("page", ["0", "1001", "not-an-integer", "1.5"])
@pytest.mark.parametrize("path", ["/chat", "/chat/direct"])
def test_chat_page_parameter_is_strict(client, user_factory, login_client, path, page):
    user_factory()
    login_client(client)

    assert client.get(path, query_string={"page": page}).status_code == 400


def test_global_history_is_scoped_hidden_filtered_fixed_and_stably_ordered(
    app, client, user_factory, login_client
):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    conversation = create_conversation(app, alice, bobby)
    start = utc_now() - timedelta(minutes=60)
    global_ids = [
        seed_message(
            app,
            alice,
            f"global-{index:02d}",
            created_at=start + timedelta(seconds=index),
        )
        for index in range(55)
    ]
    seed_message(app, alice, "hidden-global", hidden=True)
    seed_message(app, alice, "direct-only", conversation=conversation)
    login_client(client)

    first = client.get("/chat")
    second = client.get("/chat?page=2")

    assert first.status_code == second.status_code == 200
    assert first.data.count(b'data-message-id="') == 50
    assert b"global-05" in first.data
    assert b"global-54" in first.data
    assert b"global-00" not in first.data
    assert b"hidden-global" not in first.data
    assert b"direct-only" not in first.data
    assert second.data.count(b'data-message-id="') == 5
    assert global_ids[0].encode() in second.data
    assert b'data-live-enabled="false"' in second.data


def test_global_history_escapes_stored_script_body(
    app, client, user_factory, login_client
):
    alice = user_factory()
    seed_message(app, alice, "<script>alert(1)</script>")
    login_client(client)

    response = client.get("/chat")

    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in response.data
    assert b"<script>alert(1)</script>" not in response.data


def test_direct_index_only_lists_current_users_conversations_and_twenty_per_page(
    app, client, user_factory, login_client
):
    alice = user_factory("alice")
    others = [user_factory(f"user{index:02d}") for index in range(25)]
    outsider = user_factory("other_user")
    outsider_peer = user_factory("other_peer")
    for other in others:
        create_conversation(app, alice, other)
    create_conversation(app, outsider, outsider_peer)
    login_client(client)

    first = client.get("/chat/direct")
    second = client.get("/chat/direct?page=2")

    assert first.status_code == second.status_code == 200
    assert first.data.count(b"/chat/direct/") >= 20
    assert b"other_peer" not in first.data + second.data
    assert sum(name.username.encode() in first.data for name in others) == 20
    assert sum(name.username.encode() in second.data for name in others) == 5
    assert first.headers["Cache-Control"] == "no-store, private"


def test_direct_start_requires_csrf(client, user_factory, login_client):
    user_factory("alice")
    user_factory("bobby")
    login_client(client)

    response = client.post("/chat/direct/start", data={"username": "bobby"})

    assert response.status_code == 400


def test_direct_start_rejects_malformed_username_with_generic_redirect(
    client, user_factory, login_client
):
    user_factory("alice")
    login_client(client)
    token = start_token(client)

    response = client.post(
        "/chat/direct/start",
        data={"username": "bad!", "csrf_token": token},
    )

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/chat/direct")


def test_direct_start_creates_canonical_conversation_and_reuses_it(
    app, client, user_factory, login_client
):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    login_client(client)
    token = start_token(client)

    first = client.post(
        "/chat/direct/start",
        data={"username": "bobby", "csrf_token": token},
    )
    second = client.post(
        "/chat/direct/start",
        data={
            "username": "bobby",
            "user_id": str(uuid.uuid4()),
            "csrf_token": token,
        },
    )

    assert first.status_code == second.status_code == 303
    assert first.headers["Location"] == second.headers["Location"]
    with app.app_context():
        conversations = (
            db.session.execute(db.select(DirectConversation)).scalars().all()
        )
        assert len(conversations) == 1
        assert (conversations[0].user1_id, conversations[0].user2_id) == tuple(
            sorted((alice.id, bobby.id))
        )


@pytest.mark.parametrize("target_kind", ["self", "missing", "dormant"])
def test_direct_start_rejects_unavailable_targets_with_generic_error(
    client, user_factory, login_client, target_kind
):
    user_factory("alice")
    if target_kind == "dormant":
        username = user_factory("sleepy", status="dormant").username
    elif target_kind == "self":
        username = "alice"
    else:
        username = "missing"
    login_client(client)
    token = start_token(client)

    response = client.post(
        "/chat/direct/start",
        data={"username": username, "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "대화 상대를 확인할 수 없습니다.".encode() in response.data
    assert username.encode() not in response.data


def test_direct_start_blocks_dormant_current_user_at_service_boundary(
    app, user_factory
):
    alice = user_factory("alice")
    user_factory("bobby")
    with app.app_context():
        stored = db.session.get(User, alice.id)
        stored.status = "dormant"
        db.session.commit()
        result, conversation_id = start_direct_conversation(stored, "bobby")

    assert result is DirectConversationResult.TARGET_UNAVAILABLE
    assert conversation_id is None


def test_direct_start_recovers_unique_race(app, user_factory, monkeypatch):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    race_id = str(uuid.uuid4())
    user1_id, user2_id = sorted((alice.id, bobby.id))

    with app.app_context():
        original_commit = db.session.commit

        def race_commit():
            db.session.rollback()
            with db.engine.begin() as connection:
                connection.execute(
                    DirectConversation.__table__.insert().values(
                        id=race_id,
                        user1_id=user1_id,
                        user2_id=user2_id,
                        created_at=utc_now(),
                    )
                )
            raise IntegrityError("insert", {}, Exception("unique"))

        monkeypatch.setattr(db.session, "commit", race_commit)
        result, conversation_id = start_direct_conversation(alice, "bobby")
        monkeypatch.setattr(db.session, "commit", original_commit)

    assert result is DirectConversationResult.EXISTING
    assert conversation_id == race_id


def test_direct_start_database_error_rolls_back(app, user_factory, monkeypatch):
    alice = user_factory("alice")
    user_factory("bobby")
    with app.app_context():

        def fail_commit():
            raise SQLAlchemyError("private database detail")

        monkeypatch.setattr(db.session, "commit", fail_commit)
        result, conversation_id = start_direct_conversation(alice, "bobby")
        assert (
            db.session.execute(db.select(DirectConversation.id)).scalar_one_or_none()
            is None
        )

    assert result is DirectConversationResult.DATABASE_ERROR
    assert conversation_id is None


def test_direct_start_route_returns_generic_database_error(
    client, user_factory, login_client, monkeypatch
):
    user_factory("alice")
    user_factory("bobby")
    login_client(client)
    token = start_token(client)
    monkeypatch.setattr(
        "app.chat.routes.start_direct_conversation",
        lambda _user, _target: (DirectConversationResult.DATABASE_ERROR, None),
    )

    response = client.post(
        "/chat/direct/start",
        data={"username": "bobby", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "대화를 시작하지 못했습니다.".encode() in response.data


def test_direct_start_http_rate_limit(client, user_factory, login_client):
    user_factory("alice")
    user_factory("bobby")
    login_client(client)
    token = start_token(client)

    responses = [
        client.post(
            "/chat/direct/start",
            data={"username": "bobby", "csrf_token": token},
        )
        for _ in range(21)
    ]

    assert all(response.status_code == 303 for response in responses[:20])
    assert responses[20].status_code == 429


def test_direct_page_participants_allowed_nonparticipant_and_missing_share_404(
    app, user_factory, login_client
):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    user_factory("carol")
    conversation = create_conversation(app, alice, bobby)

    alice_client = app.test_client()
    bobby_client = app.test_client()
    carol_client = app.test_client()
    login_client(alice_client, username="alice")
    login_client(bobby_client, username="bobby")
    login_client(carol_client, username="carol")

    assert alice_client.get(f"/chat/direct/{conversation.id}").status_code == 200
    assert bobby_client.get(f"/chat/direct/{conversation.id}").status_code == 200
    forbidden = carol_client.get(f"/chat/direct/{conversation.id}")
    missing = carol_client.get(f"/chat/direct/{uuid.uuid4()}")
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.data == missing.data


def test_direct_page_rejects_invalid_page(app, client, user_factory, login_client):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    conversation = create_conversation(app, alice, bobby)
    login_client(client)

    assert client.get(f"/chat/direct/{conversation.id}?page=1001").status_code == 400


def test_direct_history_is_conversation_scoped_and_hidden_filtered(
    app, client, user_factory, login_client
):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    carol = user_factory("carol")
    wanted = create_conversation(app, alice, bobby)
    other = create_conversation(app, alice, carol)
    seed_message(app, alice, "wanted", conversation=wanted)
    seed_message(app, bobby, "hidden-secret-message", conversation=wanted, hidden=True)
    seed_message(app, alice, "other", conversation=other)
    seed_message(app, alice, "global")
    login_client(client)

    response = client.get(f"/chat/direct/{wanted.id}")

    assert response.status_code == 200
    assert b"wanted" in response.data
    assert b"hidden-secret-message" not in response.data
    assert b"other" not in response.data
    assert b"global" not in response.data
    assert b"user1_id" not in response.data
    assert b"auth_version" not in response.data


def test_dormant_counterpart_page_hides_live_send_form(
    app, client, user_factory, login_client
):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    conversation = create_conversation(app, alice, bobby)
    with app.app_context():
        stored = db.session.get(User, bobby.id)
        stored.status = "dormant"
        db.session.commit()
    login_client(client)

    response = client.get(f"/chat/direct/{conversation.id}")

    assert response.status_code == 200
    assert b'data-live-enabled="false"' in response.data
    assert b"data-chat-form" not in response.data


def test_chat_dtos_are_frozen_slotted_and_exclude_internal_fields(app, user_factory):
    alice = user_factory("alice")
    bobby = user_factory("bobby")
    conversation = create_conversation(app, alice, bobby)
    seed_message(app, alice, "hello", conversation=conversation)
    with app.app_context():
        history = get_message_history(
            conversation_id=conversation.id, page=1, per_page=50
        )
        conversations = list_direct_conversations(user_id=alice.id, page=1, per_page=20)
        detail = get_direct_conversation(conversation.id, alice.id)

    assert isinstance(history, ChatMessagePage)
    assert isinstance(history.items[0], ChatMessageView)
    assert isinstance(conversations, DirectConversationPage)
    assert isinstance(conversations.items[0], DirectConversationSummary)
    assert isinstance(detail, DirectConversationView)
    all_dtos = (
        history,
        history.items[0],
        conversations,
        conversations.items[0],
        detail,
    )
    forbidden = {"sender_id", "user1_id", "user2_id", "role", "auth_version", "status"}
    for dto in all_dtos:
        assert not hasattr(dto, "__dict__")
        assert forbidden.isdisjoint(field.name for field in fields(dto))
    with pytest.raises(FrozenInstanceError):
        history.items[0].body = "changed"

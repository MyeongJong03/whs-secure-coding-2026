import base64
import hashlib
import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db, socketio
from app.models import ChatMessage, DirectConversation, User


EXPECTED_DIGEST = "kzavj5fiMwLKzzD1f8S7TeoVIEi7uKHvbTA3ueZkrzYq75pNQUiUi6Dy98Q3fxb0"
VENDOR_PATH = Path("app/static/vendor/socket.io-4.8.3.min.js")


def test_local_socket_io_bundle_has_exact_sha384_and_license_banner():
    bundle = VENDOR_PATH.read_bytes()
    digest = base64.b64encode(hashlib.sha384(bundle).digest()).decode()

    assert bundle
    assert digest == EXPECTED_DIGEST
    assert bundle.startswith(b"/*!\n * Socket.IO v4.8.3")
    assert b"Released under the MIT License" in bundle[:200]


def test_templates_use_only_local_socket_io_with_matching_integrity():
    templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("app/templates/chat").glob("*.html")
    )

    assert "cdn.socket.io" not in templates
    assert "http://" not in templates
    assert "https://" not in templates
    assert "vendor/socket.io-4.8.3.min.js" in templates
    assert "socket_io_integrity" in templates
    assert templates.count("socket.io-4.8.3.min.js") == 2


def test_third_party_notice_documents_verified_local_asset():
    notice = Path("THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "Socket.IO client 4.8.3" in notice
    assert "MIT License" in notice
    assert "https://cdn.socket.io/4.8.3/socket.io.min.js" in notice
    assert EXPECTED_DIGEST in notice
    assert "locally self-hosted" in notice


@pytest.mark.parametrize(
    "requirement",
    [
        "python-socketio==5.16.3",
        "python-engineio==4.13.3",
        "simple-websocket==1.1.0",
    ],
)
def test_socket_runtime_transitive_dependencies_are_exactly_pinned(requirement):
    requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()

    assert requirements.count(requirement) == 1


def test_socket_server_uses_bounded_same_origin_threading_configuration(app):
    server = socketio.server

    assert server.async_mode == "threading"
    assert server.async_handlers is False
    assert server.always_connect is False
    assert server.eio.async_handlers is False
    assert server.eio.max_http_buffer_size == 8192
    assert server.eio.start_service_task is True
    assert server.eio.cookie is None
    assert server.eio.cors_allowed_origins is None
    assert server.eio.cors_allowed_origins not in ("*", ["*"], [])


def test_chat_namespace_registers_only_expected_handlers(app):
    handlers = socketio.server.handlers["/chat"]

    assert set(handlers) == {
        "connect",
        "disconnect",
        "chat:join_global",
        "chat:join_direct",
        "chat:send_global",
        "chat:send_direct",
    }


def test_chat_javascript_uses_safe_dom_apis_and_no_external_url():
    source = Path("app/static/js/chat.js").read_text(encoding="utf-8")

    for forbidden in (
        "innerHTML",
        "insertAdjacentHTML",
        "eval(",
        "new Function",
        "http://",
        "https://",
        "console.",
        "sender_id",
        "username:",
        "room:",
    ):
        assert forbidden not in source
    assert "createElement" in source
    assert "textContent" in source
    assert 'io("/chat"' in source
    assert "csrf_token" in source
    assert "conversation_id" in source


def test_chat_templates_have_no_inline_script_or_style():
    templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("app/templates/chat").glob("*.html")
    )
    script_tags = re.findall(r"<script\b[^>]*>", templates)

    assert script_tags
    assert all(" src=" in tag for tag in script_tags)
    assert "<style" not in templates
    assert "style=" not in templates
    assert "|safe" not in templates
    assert "Markup" not in templates


def test_chat_model_declares_named_constraint_and_indexes():
    chat_constraints = {
        constraint.name for constraint in ChatMessage.__table__.constraints
    }
    chat_indexes = {index.name for index in ChatMessage.__table__.indexes}
    direct_indexes = {index.name for index in DirectConversation.__table__.indexes}

    assert "ck_chat_messages_body_length" in chat_constraints
    assert "ck_chat_messages_is_hidden_boolean" in chat_constraints
    assert chat_indexes == {
        "ix_chat_messages_conversation_visible_created",
        "ix_chat_messages_sender_created",
    }
    assert direct_indexes == {
        "ix_direct_conversations_user1_created",
        "ix_direct_conversations_user2_created",
    }


@pytest.mark.parametrize("raw_value", [-1, 2])
def test_is_hidden_database_constraint_rejects_non_boolean_values(
    app, user_factory, raw_value
):
    user = user_factory()
    with app.app_context():
        with pytest.raises(IntegrityError):
            db.session.execute(
                text(
                    "INSERT INTO chat_messages "
                    "(id, sender_id, conversation_id, body, is_hidden, created_at) "
                    "VALUES (:id, :sender_id, NULL, :body, :is_hidden, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "sender_id": user.id,
                    "body": "invalid boolean",
                    "is_hidden": raw_value,
                },
            )
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize("raw_value", [0, 1])
def test_is_hidden_database_constraint_allows_boolean_values(
    app, user_factory, raw_value
):
    user = user_factory()
    with app.app_context():
        message_id = f"00000000-0000-0000-0000-00000000000{raw_value + 2}"
        db.session.execute(
            text(
                "INSERT INTO chat_messages "
                "(id, sender_id, conversation_id, body, is_hidden, created_at) "
                "VALUES (:id, :sender_id, NULL, :body, :is_hidden, CURRENT_TIMESTAMP)"
            ),
            {
                "id": message_id,
                "sender_id": user.id,
                "body": "valid boolean",
                "is_hidden": raw_value,
            },
        )
        db.session.commit()

        stored = db.session.execute(
            db.select(ChatMessage.is_hidden).where(ChatMessage.id == message_id)
        ).scalar_one()
        assert stored is bool(raw_value)


def test_chat_default_configuration_values(app):
    expected = {
        "CHAT_HISTORY_PER_PAGE": 50,
        "CHAT_CONVERSATIONS_PER_PAGE": 20,
        "CHAT_PAGE_MAX": 1000,
        "CHAT_MESSAGE_MAX_CHARS": 500,
        "CHAT_MESSAGE_MAX_BYTES": 2000,
        "CHAT_MESSAGE_BURST_LIMIT": 5,
        "CHAT_MESSAGE_BURST_WINDOW_SECONDS": 10,
        "CHAT_MESSAGE_HOURLY_LIMIT": 120,
        "CHAT_JOIN_LIMIT": 30,
        "CHAT_JOIN_WINDOW_SECONDS": 60,
        "CHAT_MAX_CONNECTIONS_PER_USER": 5,
        "CHAT_SOCKET_MAX_AGE_SECONDS": 1800,
    }

    assert {key: app.config[key] for key in expected} == expected


def test_chat_views_do_not_project_sensitive_user_fields():
    source = Path("app/chat/services.py").read_text(encoding="utf-8")
    forbidden_projections = (
        "User.password_hash",
        "User.role",
        "User.auth_version",
        "Wallet.balance",
    )

    assert all(field not in source for field in forbidden_projections)
    assert "db.select(User.username)" in source
    assert User.password_hash.key == "password_hash"

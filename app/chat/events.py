from flask import current_app, g, request, session
from flask_login import current_user
from flask_socketio import emit, join_room, rooms
from flask_wtf.csrf import ValidationError, validate_csrf

from app.chat.connections import (
    authenticated_chat_event,
    get_registry,
    prune_stale_connections,
)
from app.chat.policy import (
    CHAT_NAMESPACE,
    GLOBAL_ROOM,
    ack_error,
    ack_success,
    canonical_uuid,
    direct_room,
    exact_payload,
    normalize_message_body,
)
from app.chat.services import (
    MessageSaveResult,
    get_direct_conversation,
    message_payload,
    save_message,
)
from app.extensions import db, socketio
from app.models import User


LOGGABLE_EVENT_NAMES = frozenset(
    {
        "connect",
        "disconnect",
        "chat:join_global",
        "chat:join_direct",
        "chat:send_global",
        "chat:send_direct",
    }
)


def _event_limiter():
    return current_app.extensions["chat_event_limiter"]


def _connected_user() -> tuple[str, int] | None:
    session_user_id = session.get("_user_id")
    session_version = session.get("auth_version")
    if (
        not isinstance(session_user_id, str)
        or not isinstance(session_version, int)
        or isinstance(session_version, bool)
    ):
        return None
    row = db.session.execute(
        db.select(User.id, User.status, User.auth_version).where(
            User.id == session_user_id
        )
    ).one_or_none()
    if row is None or row.status != "active" or row.auth_version != session_version:
        return None
    if not current_user.is_authenticated or current_user.get_id() != row.id:
        return None
    return row.id, row.auth_version


@socketio.on("connect", namespace=CHAT_NAMESPACE)
def connect_chat(auth):
    if not isinstance(auth, dict) or frozenset(auth) != {"csrf_token"}:
        return False
    token = auth.get("csrf_token")
    if not isinstance(token, str):
        return False
    try:
        validate_csrf(token)
    except ValidationError:
        return False

    prune_stale_connections()
    identity = _connected_user()
    if identity is None:
        return False
    user_id, auth_version = identity
    record = get_registry().add(
        sid=request.sid,
        user_id=user_id,
        auth_version=auth_version,
        max_connections=current_app.config["CHAT_MAX_CONNECTIONS_PER_USER"],
    )
    return record is not None


@socketio.on("disconnect", namespace=CHAT_NAMESPACE)
def disconnect_chat(_reason=None):
    get_registry().remove(request.sid)


@socketio.on("chat:join_global", namespace=CHAT_NAMESPACE)
@authenticated_chat_event
def join_global(payload=None):
    if not _event_limiter().consume_join(g.chat_connection.user_id):
        return ack_error("rate_limited")
    if payload is not None and payload != {}:
        return ack_error("invalid_payload")
    join_room(GLOBAL_ROOM, namespace=CHAT_NAMESPACE)
    return ack_success()


@socketio.on("chat:join_direct", namespace=CHAT_NAMESPACE)
@authenticated_chat_event
def join_direct(payload=None):
    if not _event_limiter().consume_join(g.chat_connection.user_id):
        return ack_error("rate_limited")
    if not exact_payload(payload, frozenset({"conversation_id"})):
        return ack_error("invalid_payload")
    conversation_id = canonical_uuid(payload["conversation_id"])
    if conversation_id is None:
        return ack_error("invalid_payload")
    conversation = get_direct_conversation(conversation_id, g.chat_connection.user_id)
    if conversation is None:
        return ack_error("not_found")
    join_room(direct_room(conversation_id), namespace=CHAT_NAMESPACE)
    return ack_success()


def _emit_message(*, scope: str, room: str, message, conversation_id=None) -> None:
    prune_stale_connections()
    payload = {
        "scope": scope,
        "message": message_payload(message),
    }
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    socketio.emit(
        "chat:message",
        payload,
        namespace=CHAT_NAMESPACE,
        to=room,
    )


@socketio.on("chat:send_global", namespace=CHAT_NAMESPACE)
@authenticated_chat_event
def send_global(payload=None):
    if not _event_limiter().consume_message(g.chat_connection.user_id):
        return ack_error("rate_limited")
    if not exact_payload(payload, frozenset({"body"})):
        return ack_error("invalid_payload")
    validation = normalize_message_body(payload["body"])
    if not validation.valid or validation.body is None:
        return ack_error("invalid_payload")
    if GLOBAL_ROOM not in rooms(namespace=CHAT_NAMESPACE):
        return ack_error("not_joined")
    result, message = save_message(
        sender_id=g.chat_connection.user_id,
        conversation_id=None,
        body=validation.body,
    )
    if result is not MessageSaveResult.SAVED or message is None:
        return ack_error("server_error")
    _emit_message(scope="global", room=GLOBAL_ROOM, message=message)
    return ack_success()


@socketio.on("chat:send_direct", namespace=CHAT_NAMESPACE)
@authenticated_chat_event
def send_direct(payload=None):
    if not _event_limiter().consume_message(g.chat_connection.user_id):
        return ack_error("rate_limited")
    if not exact_payload(payload, frozenset({"conversation_id", "body"})):
        return ack_error("invalid_payload")
    conversation_id = canonical_uuid(payload["conversation_id"])
    validation = normalize_message_body(payload["body"])
    if conversation_id is None or not validation.valid or validation.body is None:
        return ack_error("invalid_payload")
    room = direct_room(conversation_id)
    if room not in rooms(namespace=CHAT_NAMESPACE):
        return ack_error("not_joined")
    conversation = get_direct_conversation(conversation_id, g.chat_connection.user_id)
    if conversation is None:
        return ack_error("not_found")
    if not conversation.counterpart_is_active:
        return ack_error("unavailable")
    result, message = save_message(
        sender_id=g.chat_connection.user_id,
        conversation_id=conversation_id,
        body=validation.body,
    )
    if result is not MessageSaveResult.SAVED or message is None:
        return ack_error("server_error")
    _emit_message(
        scope="direct",
        room=room,
        message=message,
        conversation_id=conversation_id,
    )
    return ack_success()


@socketio.on_error(namespace=CHAT_NAMESPACE)
def chat_error_handler(_error):
    event_name = "unknown"
    event = getattr(request, "event", None)
    if isinstance(event, dict) and isinstance(event.get("message"), str):
        candidate = event["message"]
        if candidate in LOGGABLE_EVENT_NAMES:
            event_name = candidate
    current_app.logger.warning("Unhandled chat event error: %s", event_name)
    emit("chat:error", ack_error("server_error"), namespace=CHAT_NAMESPACE)

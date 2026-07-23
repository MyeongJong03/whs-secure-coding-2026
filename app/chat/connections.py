import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from threading import RLock

from flask import current_app, g, request, session
from flask_login import current_user

from app.chat.policy import CHAT_NAMESPACE, ack_error
from app.extensions import db, socketio
from app.models import User


@dataclass(frozen=True, slots=True)
class ConnectionRecord:
    sid: str
    user_id: str
    auth_version: int
    connected_monotonic: float


class ConnectionRegistry:
    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._by_sid: dict[str, ConnectionRecord] = {}
        self._by_user: dict[str, set[str]] = defaultdict(set)
        self._lock = RLock()

    def now(self) -> float:
        return self._clock()

    def add(
        self,
        *,
        sid: str,
        user_id: str,
        auth_version: int,
        max_connections: int,
    ) -> ConnectionRecord | None:
        with self._lock:
            if len(self._by_user.get(user_id, ())) >= max_connections:
                return None
            record = ConnectionRecord(
                sid=sid,
                user_id=user_id,
                auth_version=auth_version,
                connected_monotonic=self._clock(),
            )
            self._by_sid[sid] = record
            self._by_user[user_id].add(sid)
            return record

    def get(self, sid: str) -> ConnectionRecord | None:
        with self._lock:
            return self._by_sid.get(sid)

    def remove(self, sid: str) -> ConnectionRecord | None:
        with self._lock:
            record = self._by_sid.pop(sid, None)
            if record is None:
                return None
            sockets = self._by_user.get(record.user_id)
            if sockets is not None:
                sockets.discard(sid)
                if not sockets:
                    self._by_user.pop(record.user_id, None)
            return record

    def snapshot(self) -> tuple[ConnectionRecord, ...]:
        with self._lock:
            return tuple(self._by_sid.values())

    def user_connection_count(self, user_id: str) -> int:
        with self._lock:
            return len(self._by_user.get(user_id, ()))

    def user_sockets(self, user_id: str) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._by_user.get(user_id, ()))


def get_registry() -> ConnectionRegistry:
    return current_app.extensions["chat_connection_registry"]


def _disconnect_sids(sids: tuple[str, ...]) -> None:
    registry = get_registry()
    for sid in sids:
        registry.remove(sid)
        socketio.server.disconnect(sid, namespace=CHAT_NAMESPACE)


def disconnect_user_sockets(user_id: str) -> None:
    _disconnect_sids(get_registry().user_sockets(user_id))


def prune_stale_connections() -> tuple[str, ...]:
    registry = get_registry()
    records = registry.snapshot()
    if not records:
        return ()

    user_ids = {record.user_id for record in records}
    rows = db.session.execute(
        db.select(User.id, User.status, User.auth_version).where(User.id.in_(user_ids))
    )
    users = {row.id: (row.status, row.auth_version) for row in rows}
    now = registry.now()
    max_age = current_app.config["CHAT_SOCKET_MAX_AGE_SECONDS"]
    stale = tuple(
        record.sid
        for record in records
        if record.user_id not in users
        or users[record.user_id][0] != "active"
        or users[record.user_id][1] != record.auth_version
        or now - record.connected_monotonic > max_age
    )
    _disconnect_sids(stale)
    return stale


def _terminate_current_socket() -> None:
    sid = request.sid
    get_registry().remove(sid)
    socketio.server.disconnect(sid, namespace=CHAT_NAMESPACE)


def authenticated_chat_event(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        prune_stale_connections()
        record = get_registry().get(request.sid)
        if record is None:
            _terminate_current_socket()
            return ack_error("unauthorized")

        session_user_id = session.get("_user_id")
        session_version = session.get("auth_version")
        row = db.session.execute(
            db.select(User.id, User.status, User.auth_version).where(
                User.id == record.user_id
            )
        ).one_or_none()
        if (
            row is None
            or row.status != "active"
            or row.auth_version != record.auth_version
            or session_user_id != record.user_id
            or not isinstance(session_version, int)
            or isinstance(session_version, bool)
            or session_version != row.auth_version
        ):
            _terminate_current_socket()
            return ack_error("unauthorized")

        if not current_user.is_authenticated or current_user.get_id() != record.user_id:
            _terminate_current_socket()
            return ack_error("unauthorized")

        g.chat_connection = record
        return handler(*args, **kwargs)

    return wrapped

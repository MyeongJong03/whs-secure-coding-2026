from flask import Blueprint

from app.chat.connections import ConnectionRegistry
from app.chat.rate_limit import ChatEventLimiter


bp = Blueprint("chat", __name__, url_prefix="/chat")


def init_chat_state(app) -> None:
    clock = app.config.get("CHAT_CLOCK")
    app.extensions["chat_connection_registry"] = ConnectionRegistry(clock=clock)
    app.extensions["chat_event_limiter"] = ChatEventLimiter(
        clock=clock,
        message_burst_limit=app.config["CHAT_MESSAGE_BURST_LIMIT"],
        message_burst_window=app.config["CHAT_MESSAGE_BURST_WINDOW_SECONDS"],
        message_hourly_limit=app.config["CHAT_MESSAGE_HOURLY_LIMIT"],
        join_limit=app.config["CHAT_JOIN_LIMIT"],
        join_window=app.config["CHAT_JOIN_WINDOW_SECONDS"],
    )


from app.chat import events, routes  # noqa: E402, F401

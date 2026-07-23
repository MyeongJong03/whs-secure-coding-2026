from collections.abc import Callable
from functools import wraps

from flask import Response, current_app, session
from flask_login import current_user, login_user


AUTHENTICATION_SESSION_KEYS = (
    "_user_id",
    "_fresh",
    "_id",
    "_remember",
    "auth_version",
)


def clear_authentication_session() -> None:
    for key in AUTHENTICATION_SESSION_KEYS:
        session.pop(key, None)


def establish_authenticated_session(user) -> None:
    if hasattr(user, "_get_current_object"):
        user = user._get_current_object()
    auth_version = user.auth_version
    session.clear()
    login_user(user, remember=False, fresh=True)
    session["auth_version"] = auth_version
    session.permanent = True


def private_no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store, private"
    return response


def no_store(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        return private_no_store(current_app.make_response(view(*args, **kwargs)))

    return wrapped


def authenticated_user_rate_limit_key() -> str:
    user_id = current_user.get_id()
    return f"user:{user_id}" if user_id is not None else "anonymous"

from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from app.security import no_store


def admin_required(view):
    @wraps(view)
    @login_required
    @no_store
    def wrapped(*args, **kwargs):
        if current_user.role != "admin" or current_user.status != "active":
            abort(403)
        return view(*args, **kwargs)

    return wrapped

from flask import Blueprint


bp = Blueprint("moderation", __name__)


from app.moderation import routes  # noqa: E402, F401

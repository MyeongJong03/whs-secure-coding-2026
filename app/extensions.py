import sqlite3

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.session_protection = "strong"
csrf = CSRFProtect()
socketio = SocketIO(
    async_mode="threading",
    async_handlers=False,
    always_connect=False,
    max_http_buffer_size=8192,
    monitor_clients=True,
    logger=False,
    engineio_logger=False,
    cors_allowed_origins=None,
)
limiter = Limiter(key_func=get_remote_address)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

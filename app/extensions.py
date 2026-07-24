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

from app.filesystem import secure_sqlite_database_file

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
        main_database_path = None
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA database_list")
            main_database_path = next(
                (
                    database_path
                    for _sequence, name, database_path in cursor.fetchall()
                    if name == "main"
                ),
                None,
            )
        finally:
            cursor.close()
        secure_sqlite_database_file(main_database_path)

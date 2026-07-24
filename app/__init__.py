import os
import secrets

from flask import Flask, render_template, request, session
from werkzeug.security import generate_password_hash

from app.config import CONFIGS, validate_secret_key
from app.extensions import csrf, db, limiter, login_manager, migrate, socketio
from app.filesystem import secure_instance_directory


def create_app(
    config_name: str | None = None, test_config: dict | None = None
) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    selected_config = (config_name or os.getenv("FLASK_CONFIG", "development")).lower()
    config_class = CONFIGS.get(selected_config)
    if config_class is None:
        raise ValueError(f"Unknown application configuration: {selected_config}")

    app.config.from_object(config_class)
    if selected_config != "testing":
        app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
        app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
            "DATABASE_URL", app.config["SQLALCHEMY_DATABASE_URI"]
        )
        app.config["RATELIMIT_STORAGE_URI"] = os.getenv(
            "RATELIMIT_STORAGE_URI", app.config["RATELIMIT_STORAGE_URI"]
        )
    if selected_config == "development":
        app.config["DEBUG"] = os.getenv("FLASK_DEBUG", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if test_config:
        app.config.update(test_config)
    if selected_config != "testing":
        app.config["SECRET_KEY"] = validate_secret_key(app.config.get("SECRET_KEY"))
    secure_instance_directory(app.instance_path)
    if app.config.get("PRODUCT_UPLOAD_DIR") is None:
        app.config["PRODUCT_UPLOAD_DIR"] = os.path.join(
            app.instance_path, "uploads", "products"
        )

    db.init_app(app)
    migrate.init_app(app, db, compare_type=True, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app)
    limiter.init_app(app)

    from app.main import bp as main_bp
    from app.admin import bp as admin_bp
    from app.cli import register_cli
    from app.auth import bp as auth_bp
    from app.chat import bp as chat_bp
    from app.chat import init_chat_state
    from app.models import User
    from app.products import bp as products_bp
    from app.moderation import bp as moderation_bp
    from app.security import clear_authentication_session
    from app.users import bp as users_bp
    from app.wallet import bp as wallet_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(moderation_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(wallet_bp)
    register_cli(app)
    init_chat_state(app)
    app.extensions["auth_dummy_hash"] = generate_password_hash(
        secrets.token_urlsafe(32)
    )

    @login_manager.user_loader
    def load_user(user_id: str):
        user = db.session.get(User, user_id)
        session_auth_version = session.get("auth_version")
        if (
            user is None
            or user.status != "active"
            or session_auth_version is None
            or not isinstance(session_auth_version, int)
            or isinstance(session_auth_version, bool)
            or session_auth_version != user.auth_version
        ):
            clear_authentication_session()
            return None
        return user

    register_security_headers(app)
    register_error_handlers(app)
    return app


def register_security_headers(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response):
        if (
            request.path.startswith("/auth/")
            or request.path == "/me"
            or request.path.startswith("/me/")
            or request.path == "/chat"
            or request.path.startswith("/chat/")
            or request.path == "/reports"
            or request.path.startswith("/reports/")
            or request.path == "/admin"
            or request.path.startswith("/admin/")
            or request.path == "/wallet"
            or request.path.startswith("/wallet/")
        ):
            response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "microphone=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self' ws: wss:; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
            "form-action 'self'"
        )
        return response


def register_error_handlers(app: Flask) -> None:
    for status_code in (400, 403, 404, 405, 409, 413, 429):
        app.register_error_handler(
            status_code,
            lambda _error, code=status_code: (
                render_template("errors/error.html", code=code),
                code,
            ),
        )

    @app.errorhandler(500)
    def internal_server_error(_error):
        db.session.rollback()
        return render_template("errors/error.html", code=500), 500

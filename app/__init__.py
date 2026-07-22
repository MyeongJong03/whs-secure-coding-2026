import os

from flask import Flask, render_template

from app.config import CONFIGS, validate_secret_key
from app.extensions import csrf, db, limiter, login_manager, migrate, socketio


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

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db, compare_type=True, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app)
    limiter.init_app(app)

    from app.main import bp as main_bp
    from app.models import User

    app.register_blueprint(main_bp)

    @login_manager.user_loader
    def load_user(user_id: str):
        user = db.session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user

    register_security_headers(app)
    register_error_handlers(app)
    return app


def register_security_headers(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response):
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
    for status_code in (400, 403, 404, 429):
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

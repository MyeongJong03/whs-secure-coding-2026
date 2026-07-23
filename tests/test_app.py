import secrets
from pathlib import Path

import pytest
from flask import jsonify
from flask_login import current_user

from app import create_app
from app.extensions import db
from app.models import User


def test_testing_config_creates_application():
    app = create_app("testing")

    assert app.testing is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


@pytest.mark.parametrize("config_name", ["development", "production"])
def test_missing_secret_key_fails_safely(monkeypatch, config_name):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FLASK_CONFIG", raising=False)

    with pytest.raises(RuntimeError, match="SECRET_KEY must be a random string"):
        create_app(config_name)


@pytest.mark.parametrize("config_name", ["development", "production"])
@pytest.mark.parametrize(
    "unsafe_key",
    [
        "",
        "   ",
        "short-key",
        "replace-with-a-long-random-local-value",
        "secret" + "!",
    ],
    ids=[
        "empty",
        "whitespace-only",
        "short",
        "env-example-placeholder",
        "legacy-fixed-value",
    ],
)
def test_unsafe_secret_key_fails_safely(monkeypatch, config_name, unsafe_key):
    monkeypatch.setenv("SECRET_KEY", unsafe_key)

    with pytest.raises(RuntimeError, match="SECRET_KEY must be a random string"):
        create_app(config_name)


@pytest.mark.parametrize("config_name", ["development", "production"])
def test_non_string_secret_key_fails_safely(monkeypatch, config_name):
    monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(32))

    with pytest.raises(RuntimeError, match="SECRET_KEY must be a random string"):
        create_app(config_name, {"SECRET_KEY": 12345})


@pytest.mark.parametrize("config_name", ["development", "production"])
def test_random_secret_key_of_at_least_32_characters_is_allowed(
    monkeypatch, config_name
):
    random_key = secrets.token_urlsafe(32)
    monkeypatch.setenv("SECRET_KEY", random_key)

    app = create_app(config_name)

    assert app.config["SECRET_KEY"] == random_key


def test_secret_key_is_validated_after_trimming(monkeypatch):
    random_key = secrets.token_urlsafe(32)
    monkeypatch.setenv("SECRET_KEY", f"  {random_key}  ")

    app = create_app("development")

    assert app.config["SECRET_KEY"] == random_key


def test_csrf_extension_is_active_in_testing(app):
    assert app.config["WTF_CSRF_ENABLED"] is True
    assert "csrf" in app.extensions


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_index_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Secure Market" in response.data


def test_security_headers_are_applied(client):
    response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "camera=()" in response.headers["Permissions-Policy"]
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_404_does_not_expose_internal_details(client):
    response = client.get("/missing-private-path")

    assert response.status_code == 404
    assert b"Traceback" not in response.data
    assert b"/home/" not in response.data


def test_500_does_not_expose_internal_details(app, client):
    marker = "INTERNAL_DATABASE_CREDENTIAL"

    @app.get("/test-error")
    def test_error():
        raise RuntimeError(marker)

    response = client.get("/test-error")

    assert response.status_code == 500
    assert marker.encode() not in response.data
    assert b"Traceback" not in response.data
    assert b"/home/" not in response.data


def test_legacy_fixed_secret_is_absent_from_application_source():
    forbidden = "secret" + "!"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("app").rglob("*.py")
    )

    assert forbidden not in source


def register_auth_state_route(app):
    @app.get("/_test/auth-state")
    def auth_state():
        return jsonify(authenticated=current_user.is_authenticated)


def test_active_session_user_is_loaded_as_authenticated(
    app, client, user_factory, login_client
):
    register_auth_state_route(app)
    user_factory()
    assert login_client(client).status_code == 303

    response = client.get("/_test/auth-state")

    assert response.status_code == 200
    assert response.get_json() == {"authenticated": True}


def test_dormant_status_invalidates_existing_session_on_next_request(
    app, client, user_factory, login_client
):
    register_auth_state_route(app)
    user = user_factory()
    user_id = user.id
    assert login_client(client).status_code == 303
    assert client.get("/_test/auth-state").get_json() == {"authenticated": True}

    with app.app_context():
        user = db.session.get(User, user_id)
        user.status = "dormant"
        db.session.commit()

    response = client.get("/_test/auth-state")

    assert response.status_code == 200
    assert response.get_json() == {"authenticated": False}

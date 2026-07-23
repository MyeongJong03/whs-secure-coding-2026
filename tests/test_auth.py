from http import HTTPStatus
from html.parser import HTMLParser

import pytest
from flask import jsonify
from flask_login import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.services import (
    RegistrationResult,
    authenticate_user,
    register_user,
)
from app.extensions import db
from app.models import User, Wallet
from app.security import AUTHENTICATION_SESSION_KEYS


TEST_PASSWORD = "valid-test-password-123"
NEW_TEST_PASSWORD = "new-valid-password-456"


def register(
    client,
    csrf_token,
    *,
    username="alice",
    password=TEST_PASSWORD,
    password_confirm=TEST_PASSWORD,
    extra=None,
):
    token = csrf_token(client, "/auth/register")
    data = {
        "username": username,
        "password": password,
        "password_confirm": password_confirm,
        "csrf_token": token,
    }
    data.update(extra or {})
    return client.post("/auth/register", data=data)


def auth_state_route(app):
    @app.get("/_test/current-auth-state")
    def current_auth_state():
        return jsonify(authenticated=current_user.is_authenticated)


class ResponseStructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.structure = []

    def handle_starttag(self, tag, attrs):
        self.structure.append(("start", tag, tuple(name for name, _value in attrs)))

    def handle_endtag(self, tag):
        self.structure.append(("end", tag))


def response_structure(response):
    parser = ResponseStructureParser()
    parser.feed(response.get_data(as_text=True))
    return parser.structure


def test_register_get_is_available_and_private(client):
    response = client.get("/auth/register")

    assert response.status_code == 200
    assert b"Cache-Control" not in response.data
    assert response.headers["Cache-Control"] == "no-store, private"


def test_register_post_requires_csrf(client):
    response = client.post(
        "/auth/register",
        data={
            "username": "alice",
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
        },
    )

    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "no-store, private"


def test_register_creates_user_wallet_and_redirects(app, client, csrf_token):
    response = register(client, csrf_token, username="  alice  ")

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/auth/login")
    with app.app_context():
        user = db.session.execute(
            db.select(User).where(User.username == "alice")
        ).scalar_one()
        assert user.role == "user"
        assert user.status == "active"
        assert user.auth_version == 1
        assert user.wallet.balance == 100000
        assert user.password_hash != TEST_PASSWORD
        assert user.check_password(TEST_PASSWORD)
        assert db.session.execute(db.select(Wallet)).scalars().all() == [user.wallet]


def test_registration_does_not_automatically_log_user_in(client, csrf_token):
    assert register(client, csrf_token).status_code == 303

    assert client.get("/me").status_code == 302


def test_same_password_produces_distinct_scrypt_hashes(app, client, csrf_token):
    assert register(client, csrf_token, username="alice").status_code == 303
    assert register(client, csrf_token, username="bobby").status_code == 303

    with app.app_context():
        users = (
            db.session.execute(db.select(User).order_by(User.username)).scalars().all()
        )
        assert users[0].password_hash.startswith("scrypt:")
        assert users[1].password_hash.startswith("scrypt:")
        assert users[0].password_hash != users[1].password_hash


def test_password_whitespace_is_not_stripped_during_registration_or_login(
    app, client, csrf_token, login_client
):
    spaced_password = "  spaced-test-password  "
    assert (
        register(
            client,
            csrf_token,
            password=spaced_password,
            password_confirm=spaced_password,
        ).status_code
        == 303
    )
    with app.app_context():
        user = db.session.execute(db.select(User)).scalar_one()
        assert user.check_password(spaced_password)
        assert not user.check_password(spaced_password.strip())

    assert login_client(client, password=spaced_password).status_code == 303


@pytest.mark.parametrize(
    "username",
    ["abc", "a" * 33, "bad-name", "bad name", "한글이름"],
)
def test_registration_rejects_invalid_username(client, csrf_token, username):
    response = register(client, csrf_token, username=username)

    assert response.status_code == 400


@pytest.mark.parametrize("password", ["a" * 11, "a" * 129])
def test_registration_rejects_password_outside_length_policy(
    client, csrf_token, password
):
    response = register(
        client,
        csrf_token,
        password=password,
        password_confirm=password,
    )

    assert response.status_code == 400
    assert password.encode() not in response.data


@pytest.mark.parametrize("password_confirm", ["c" * 11, "c" * 129])
def test_registration_rejects_confirmation_outside_length_policy(
    app, client, csrf_token, password_confirm
):
    response = register(
        client,
        csrf_token,
        password=TEST_PASSWORD,
        password_confirm=password_confirm,
    )

    assert response.status_code == 400
    assert TEST_PASSWORD.encode() not in response.data
    assert password_confirm.encode() not in response.data
    with app.app_context():
        assert db.session.execute(db.select(User)).scalar_one_or_none() is None
        assert db.session.execute(db.select(Wallet)).scalar_one_or_none() is None


def test_registration_rejects_password_confirmation_mismatch(app, client, csrf_token):
    response = register(
        client,
        csrf_token,
        password_confirm="different-test-password-999",
    )

    assert response.status_code == 400
    assert TEST_PASSWORD.encode() not in response.data
    with app.app_context():
        assert db.session.execute(db.select(User)).scalar_one_or_none() is None
        assert db.session.execute(db.select(Wallet)).scalar_one_or_none() is None


def test_duplicate_registration_is_safe_and_atomic(app, client, csrf_token):
    assert register(client, csrf_token).status_code == 303

    response = register(client, csrf_token)

    assert response.status_code == 400
    assert b"ck_users" not in response.data
    assert b"UNIQUE constraint" not in response.data
    assert b"Traceback" not in response.data
    with app.app_context():
        assert db.session.execute(db.select(User)).scalars().all().__len__() == 1
        assert db.session.execute(db.select(Wallet)).scalars().all().__len__() == 1


def test_registration_ignores_privilege_and_wallet_fields(app, client, csrf_token):
    response = register(
        client,
        csrf_token,
        extra={
            "role": "admin",
            "status": "dormant",
            "auth_version": "999",
            "balance": "999999999",
        },
    )

    assert response.status_code == 303
    with app.app_context():
        user = db.session.execute(db.select(User)).scalar_one()
        assert (user.role, user.status, user.auth_version) == ("user", "active", 1)
        assert user.wallet.balance == 100000


def test_registration_rolls_back_user_and_wallet_on_database_error(
    app, client, csrf_token, monkeypatch
):
    def fail_commit():
        raise SQLAlchemyError("simulated")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = register(client, csrf_token)

    assert response.status_code == 400
    assert b"simulated" not in response.data
    with app.app_context():
        assert db.session.execute(db.select(User)).scalar_one_or_none() is None
        assert db.session.execute(db.select(Wallet)).scalar_one_or_none() is None


def test_registration_integrity_race_is_rolled_back(app, monkeypatch):
    with app.app_context():

        def fail_commit():
            raise IntegrityError("insert", {}, RuntimeError("unique race"))

        monkeypatch.setattr(db.session, "commit", fail_commit)

        result = register_user("alice", TEST_PASSWORD)

        assert result is RegistrationResult.DUPLICATE_USERNAME
        assert not db.session.new


def test_registration_rate_limit_is_post_only(client, csrf_token):
    for _ in range(10):
        assert client.get("/auth/register").status_code == 200
    token = csrf_token(client, "/auth/register")
    data = {
        "username": "alice",
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
        "csrf_token": token,
    }
    responses = [client.post("/auth/register", data=data) for _ in range(6)]

    assert [response.status_code for response in responses[:5]] == [
        303,
        400,
        400,
        400,
        400,
    ]
    assert responses[5].status_code == 429
    assert b"Traceback" not in responses[5].data


def test_login_get_is_available_and_private(client):
    response = client.get("/auth/login")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"


def test_login_post_requires_csrf(client):
    response = client.post(
        "/auth/login", data={"username": "alice", "password": TEST_PASSWORD}
    )

    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "no-store, private"


def test_malformed_login_uses_generic_error_without_reflecting_password(
    client, csrf_token
):
    submitted_password = "malformed-login-password"
    token = csrf_token(client, "/auth/login")

    response = client.post(
        "/auth/login",
        data={
            "username": "bad-name",
            "password": submitted_password,
            "csrf_token": token,
        },
    )

    assert response.status_code == 401
    assert "사용자명 또는 비밀번호가 올바르지 않습니다." in response.get_data(
        as_text=True
    )
    assert submitted_password.encode() not in response.data


def test_active_user_can_login_with_versioned_permanent_session(
    client, user_factory, login_client
):
    user_factory()

    response = login_client(client)

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/me")
    assert "remember_token" not in response.headers.get("Set-Cookie", "")
    with client.session_transaction() as login_session:
        assert login_session["auth_version"] == 1
        assert login_session.permanent is True


def test_login_trims_username(client, user_factory, csrf_token):
    user_factory()
    token = csrf_token(client, "/auth/login")

    response = client.post(
        "/auth/login",
        data={
            "username": "  alice  ",
            "password": TEST_PASSWORD,
            "csrf_token": token,
        },
    )

    assert response.status_code == 303


@pytest.mark.parametrize("case", ["wrong-password", "missing-user", "dormant-user"])
def test_login_failure_uses_same_generic_response(
    client, user_factory, csrf_token, case
):
    if case == "dormant-user":
        user_factory(status="dormant")
        username = "alice"
        password = TEST_PASSWORD
    elif case == "missing-user":
        username = "ghost"
        password = TEST_PASSWORD
    else:
        user_factory()
        username = "alice"
        password = "wrong-test-password-000"
    token = csrf_token(client, "/auth/login")

    response = client.post(
        "/auth/login",
        data={"username": username, "password": password, "csrf_token": token},
    )

    assert response.status_code == 401
    assert "사용자명 또는 비밀번호가 올바르지 않습니다." in response.get_data(
        as_text=True
    )
    assert "존재하지" not in response.get_data(as_text=True)
    assert "휴면" not in response.get_data(as_text=True)
    assert password.encode() not in response.data
    assert b'<form method="post"' in response.data


def test_login_failure_cases_have_identical_status_message_and_html_structure(
    app, user_factory, csrf_token
):
    user_factory(username="alice")
    user_factory(username="sleepy", status="dormant")
    cases = (
        ("alice", "wrong-test-password-000"),
        ("ghost", TEST_PASSWORD),
        ("sleepy", TEST_PASSWORD),
    )
    responses = []
    for username, password in cases:
        test_client = app.test_client()
        token = csrf_token(test_client, "/auth/login")
        responses.append(
            test_client.post(
                "/auth/login",
                data={
                    "username": username,
                    "password": password,
                    "csrf_token": token,
                },
            )
        )

    assert {response.status_code for response in responses} == {401}
    assert len({tuple(response_structure(response)) for response in responses}) == 1
    for response in responses:
        assert "사용자명 또는 비밀번호가 올바르지 않습니다." in response.get_data(
            as_text=True
        )


def test_missing_and_dormant_login_use_application_dummy_hash(
    app, user_factory, monkeypatch
):
    user_factory(username="sleepy", status="dormant")
    verified_hashes = []

    def record_dummy_verification(encoded_hash, _candidate):
        verified_hashes.append(encoded_hash)
        return False

    monkeypatch.setattr(
        "app.auth.services.check_password_hash", record_dummy_verification
    )
    with app.app_context():
        assert authenticate_user("ghost", TEST_PASSWORD) is None
        assert authenticate_user("sleepy", TEST_PASSWORD) is None
        dummy_hash = app.extensions["auth_dummy_hash"]

    assert verified_hashes == [dummy_hash, dummy_hash]


def test_login_clears_pre_authentication_session_state(
    client, user_factory, csrf_token
):
    user_factory()
    token = csrf_token(client, "/auth/login")
    with client.session_transaction() as login_session:
        login_session["untrusted_marker"] = "remove-me"

    response = client.post(
        "/auth/login",
        data={"username": "alice", "password": TEST_PASSWORD, "csrf_token": token},
    )

    assert response.status_code == 303
    with client.session_transaction() as login_session:
        assert "untrusted_marker" not in login_session


def test_login_ignores_external_next_url(client, user_factory, csrf_token):
    user_factory()
    token = csrf_token(client, "/auth/login?next=https://example.invalid/steal")

    response = client.post(
        "/auth/login?next=https://example.invalid/steal",
        data={"username": "alice", "password": TEST_PASSWORD, "csrf_token": token},
    )

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/me")
    assert "example.invalid" not in response.headers["Location"]


def test_authenticated_user_is_redirected_from_login_and_register(
    client, user_factory, login_client
):
    user_factory()
    assert login_client(client).status_code == 303

    assert client.get("/auth/login").status_code == 303
    assert client.get("/auth/register").status_code == 303


def test_login_rate_limit_returns_safe_429(client, csrf_token):
    token = csrf_token(client, "/auth/login")
    data = {"username": "ghost", "password": TEST_PASSWORD, "csrf_token": token}
    responses = [client.post("/auth/login", data=data) for _ in range(6)]

    assert all(response.status_code == 401 for response in responses[:5])
    assert responses[5].status_code == 429
    assert b"Traceback" not in responses[5].data
    assert TEST_PASSWORD.encode() not in responses[5].data


def test_logout_is_post_only_and_requires_csrf(client, user_factory, login_client):
    user_factory()
    assert login_client(client).status_code == 303

    assert client.get("/auth/logout").status_code == 405
    response = client.post("/auth/logout")
    assert response.status_code == 400


def test_valid_logout_clears_authenticated_session(
    app, client, user_factory, login_client, csrf_token
):
    auth_state_route(app)
    user_factory()
    assert login_client(client).status_code == 303
    token = csrf_token(client, "/me")

    response = client.post("/auth/logout", data={"csrf_token": token})

    assert response.status_code == 303
    assert client.get("/_test/current-auth-state").get_json() == {
        "authenticated": False
    }
    with client.session_transaction() as login_session:
        assert not any(key in login_session for key in AUTHENTICATION_SESSION_KEYS)


def test_active_versioned_session_is_authenticated(client, user_factory, login_client):
    user_factory()
    assert login_client(client).status_code == 303

    assert client.get("/me").status_code == 200


@pytest.mark.parametrize("condition", ["missing", "mismatch", "wrong-type"])
def test_invalid_auth_version_rejects_and_purges_authentication_keys(
    client, user_factory, login_client, condition
):
    user_factory()
    assert login_client(client).status_code == 303
    with client.session_transaction() as login_session:
        if condition == "missing":
            login_session.pop("auth_version")
        elif condition == "mismatch":
            login_session["auth_version"] = 999
        else:
            login_session["auth_version"] = "1"

    response = client.get("/me")

    assert response.status_code == 302
    with client.session_transaction() as login_session:
        assert not any(key in login_session for key in AUTHENTICATION_SESSION_KEYS)


def test_dormant_session_does_not_resurrect_after_reactivation(
    app, client, user_factory, login_client
):
    user = user_factory()
    assert login_client(client).status_code == 303
    with app.app_context():
        stored_user = db.session.get(User, user.id)
        stored_user.status = "dormant"
        db.session.commit()

    assert client.get("/me").status_code == 302
    with app.app_context():
        stored_user = db.session.get(User, user.id)
        stored_user.status = "active"
        db.session.commit()

    assert client.get("/me").status_code == 302


def test_deleted_user_session_is_rejected_and_purged(
    app, client, user_factory, login_client
):
    user = user_factory()
    assert login_client(client).status_code == 303
    with app.app_context():
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()

    assert client.get("/me").status_code == 302
    with client.session_transaction() as login_session:
        assert not any(key in login_session for key in AUTHENTICATION_SESSION_KEYS)


def test_session_cookie_security_attributes(client, user_factory, login_client):
    user_factory()

    response = login_client(client)
    cookie = response.headers.get("Set-Cookie", "")

    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" not in cookie


def test_production_cookie_is_secure(monkeypatch):
    from app import create_app

    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    application = create_app("production", {"SQLALCHEMY_DATABASE_URI": "sqlite://"})

    assert application.config["SESSION_COOKIE_SECURE"] is True


def test_login_manager_uses_strong_session_protection(app):
    assert app.login_manager.session_protection == "strong"
    assert app.login_manager.login_view == "auth.login"


def test_password_change_requires_csrf(client, user_factory, login_client):
    user_factory()
    assert login_client(client).status_code == 303

    response = client.post(
        "/me/password",
        data={
            "current_password": TEST_PASSWORD,
            "new_password": NEW_TEST_PASSWORD,
            "new_password_confirm": NEW_TEST_PASSWORD,
        },
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("current_password", "new_password", "confirmation"),
    [
        ("wrong-current-password", NEW_TEST_PASSWORD, NEW_TEST_PASSWORD),
        (TEST_PASSWORD, NEW_TEST_PASSWORD, "different-new-password"),
        (TEST_PASSWORD, "a" * 11, "a" * 11),
        (TEST_PASSWORD, "a" * 129, "a" * 129),
        (TEST_PASSWORD, NEW_TEST_PASSWORD, "c" * 11),
        (TEST_PASSWORD, NEW_TEST_PASSWORD, "c" * 129),
        (TEST_PASSWORD, TEST_PASSWORD, TEST_PASSWORD),
    ],
)
def test_invalid_password_change_preserves_hash_and_version(
    app,
    client,
    user_factory,
    login_client,
    csrf_token,
    current_password,
    new_password,
    confirmation,
):
    user = user_factory()
    assert login_client(client).status_code == 303
    with app.app_context():
        original_hash = db.session.get(User, user.id).password_hash
    token = csrf_token(client, "/me")

    response = client.post(
        "/me/password",
        data={
            "current_password": current_password,
            "new_password": new_password,
            "new_password_confirm": confirmation,
            "csrf_token": token,
        },
    )

    assert response.status_code == 400
    assert current_password.encode() not in response.data
    assert new_password.encode() not in response.data
    assert confirmation.encode() not in response.data
    with app.app_context():
        stored_user = db.session.get(User, user.id)
        assert stored_user.password_hash == original_hash
        assert stored_user.auth_version == 1


def test_password_change_rotates_hash_and_version_and_keeps_current_client(
    app, client, user_factory, login_client, csrf_token
):
    user = user_factory()
    assert login_client(client).status_code == 303
    with app.app_context():
        original_hash = db.session.get(User, user.id).password_hash
    token = csrf_token(client, "/me")

    response = client.post(
        "/me/password",
        data={
            "current_password": TEST_PASSWORD,
            "new_password": NEW_TEST_PASSWORD,
            "new_password_confirm": NEW_TEST_PASSWORD,
            "csrf_token": token,
        },
    )

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/me")
    assert client.get("/me").status_code == 200
    with client.session_transaction() as login_session:
        assert login_session["auth_version"] == 2
        assert login_session.permanent
    with app.app_context():
        stored_user = db.session.get(User, user.id)
        assert stored_user.password_hash != original_hash
        assert stored_user.auth_version == 2
        assert not stored_user.check_password(TEST_PASSWORD)
        assert stored_user.check_password(NEW_TEST_PASSWORD)


def test_password_change_invalidates_other_client_and_updates_login_credentials(
    app, client, user_factory, login_client, csrf_token
):
    user_factory()
    other_client = app.test_client()
    assert login_client(client).status_code == 303
    assert login_client(other_client).status_code == 303
    token = csrf_token(client, "/me")
    assert (
        client.post(
            "/me/password",
            data={
                "current_password": TEST_PASSWORD,
                "new_password": NEW_TEST_PASSWORD,
                "new_password_confirm": NEW_TEST_PASSWORD,
                "csrf_token": token,
            },
        ).status_code
        == 303
    )

    assert other_client.get("/me").status_code == 302
    old_password_client = app.test_client()
    new_password_client = app.test_client()
    assert login_client(old_password_client).status_code == 401
    assert (
        login_client(new_password_client, password=NEW_TEST_PASSWORD).status_code == 303
    )


def test_password_change_rate_limit_is_per_user(
    client, user_factory, login_client, csrf_token
):
    user_factory()
    assert login_client(client).status_code == 303
    token = csrf_token(client, "/me")
    data = {
        "current_password": "wrong-current-password",
        "new_password": NEW_TEST_PASSWORD,
        "new_password_confirm": NEW_TEST_PASSWORD,
        "csrf_token": token,
    }
    responses = [client.post("/me/password", data=data) for _ in range(6)]

    assert all(response.status_code == 400 for response in responses[:5])
    assert responses[5].status_code == HTTPStatus.TOO_MANY_REQUESTS


def test_password_change_database_error_rolls_back_and_is_not_exposed(
    app, client, user_factory, login_client, csrf_token, monkeypatch
):
    user = user_factory()
    assert login_client(client).status_code == 303
    token = csrf_token(client, "/me")
    with app.app_context():
        original_hash = db.session.get(User, user.id).password_hash

    def fail_commit():
        raise SQLAlchemyError("private password database detail")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = client.post(
        "/me/password",
        data={
            "current_password": TEST_PASSWORD,
            "new_password": NEW_TEST_PASSWORD,
            "new_password_confirm": NEW_TEST_PASSWORD,
            "csrf_token": token,
        },
    )

    assert response.status_code == 400
    assert b"private password database detail" not in response.data
    with app.app_context():
        stored_user = db.session.get(User, user.id)
        assert stored_user.password_hash == original_hash
        assert stored_user.auth_version == 1

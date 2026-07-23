import pytest
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash

from app.cli import create_admin
from app.extensions import db
from app.models import AuditLog, User, Wallet


VALID_PASSWORD = "a-secure-admin-password"


def test_create_admin_command_is_registered(app):
    assert "create-admin" in app.cli.list_commands(app)


def test_create_admin_creates_atomic_admin_wallet_and_audit(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        create_admin,
        ["--username", " secure_admin "],
        input=f"{VALID_PASSWORD}\n{VALID_PASSWORD}\n",
    )
    assert result.exit_code == 0
    assert "Admin account created: secure_admin" in result.output
    assert VALID_PASSWORD not in result.output
    with app.app_context():
        admin = db.session.execute(
            db.select(User).where(User.username == "secure_admin")
        ).scalar_one()
        assert admin.role == "admin"
        assert admin.status == "active"
        assert admin.auth_version == 1
        assert admin.password_hash.startswith("scrypt:")
        assert check_password_hash(admin.password_hash, VALID_PASSWORD)
        assert VALID_PASSWORD not in admin.password_hash
        assert db.session.get(Wallet, admin.id).balance == 100000
        audit = db.session.execute(
            db.select(AuditLog).where(AuditLog.action == "admin.account_created")
        ).scalar_one()
        assert audit.actor_user_id is None
        assert audit.details == {"username": "secure_admin"}


@pytest.mark.parametrize(
    ("password", "confirmation"),
    [
        ("a" * 11, "a" * 11),
        ("a" * 129, "a" * 129),
        (VALID_PASSWORD, "different-secure-password"),
    ],
)
def test_create_admin_rejects_invalid_password_without_outputting_it(
    app, password, confirmation
):
    result = app.test_cli_runner().invoke(
        create_admin,
        ["--username", "secure_admin"],
        input=f"{password}\n{confirmation}\n",
    )
    assert result.exit_code != 0
    assert password not in result.output
    assert confirmation not in result.output
    with app.app_context():
        assert db.session.execute(db.select(User.id)).all() == []


@pytest.mark.parametrize(
    "username",
    ["abc", "bad-name", "x" * 33, "<script>"],
)
def test_create_admin_rejects_invalid_username(app, username):
    result = app.test_cli_runner().invoke(
        create_admin,
        ["--username", username],
    )
    assert result.exit_code != 0
    with app.app_context():
        assert db.session.execute(db.select(User.id)).all() == []


def test_create_admin_rejects_duplicate_without_promoting_existing_user(
    app, user_factory
):
    existing = user_factory("duplicate")
    result = app.test_cli_runner().invoke(
        create_admin,
        ["--username", "duplicate"],
    )
    assert result.exit_code != 0
    with app.app_context():
        stored = db.session.get(User, existing.id)
        assert stored.role == "user"
        assert (
            db.session.execute(db.select(Wallet).where(Wallet.user_id == existing.id))
            .scalars()
            .all()
            .__len__()
            == 1
        )
        assert db.session.execute(db.select(AuditLog.id)).all() == []


def test_create_admin_commit_failure_rolls_back_everything(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            db.session,
            "commit",
            lambda: (_ for _ in ()).throw(SQLAlchemyError("private sql")),
        )
        result = app.test_cli_runner().invoke(
            create_admin,
            ["--username", "secure_admin"],
            input=f"{VALID_PASSWORD}\n{VALID_PASSWORD}\n",
        )
        assert result.exit_code != 0
        assert "private sql" not in result.output
        assert VALID_PASSWORD not in result.output
        assert db.session.execute(db.select(User.id)).all() == []
        assert db.session.execute(db.select(Wallet.user_id)).all() == []
        assert db.session.execute(db.select(AuditLog.id)).all() == []


def test_create_admin_has_no_plaintext_password_option(app):
    result = app.test_cli_runner().invoke(create_admin, ["--help"])
    assert result.exit_code == 0
    assert "--username" in result.output
    assert "--password" not in result.output

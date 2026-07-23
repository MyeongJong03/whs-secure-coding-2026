import os
import secrets
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User


FIRST_REVISION = "09357cac1cb7"
SECOND_REVISION = "57c21fbc6f83"
THIRD_REVISION = "c3d57de11bfa"
FOURTH_REVISION = "a91f4c8d2e70"
FIFTH_REVISION = "e5b7a2c9d4f1"
FIRST_MIGRATION = Path(
    "migrations/versions/09357cac1cb7_create_secure_foundation_models.py"
)
SECOND_MIGRATION = Path(
    "migrations/versions/57c21fbc6f83_add_authentication_version_to_users.py"
)
THIRD_MIGRATION = Path(
    "migrations/versions/c3d57de11bfa_add_secure_product_constraints_and_indexes.py"
)
FOURTH_MIGRATION = Path(
    "migrations/versions/a91f4c8d2e70_add_secure_chat_constraints_and_indexes.py"
)
FIFTH_MIGRATION = Path(
    "migrations/versions/e5b7a2c9d4f1_add_secure_moderation_and_audit_metadata.py"
)


def run_flask(database_path: Path, *arguments: str) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path}",
            "FLASK_CONFIG": "development",
            "SECRET_KEY": secrets.token_urlsafe(48),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "flask", "--app", "run.py", *arguments],
        check=False,
        capture_output=True,
        cwd=Path.cwd(),
        env=environment,
        text=True,
        timeout=60,
    )


def assert_flask_success(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def test_auth_version_defaults_to_one(app):
    with app.app_context():
        user = User(username="alice", password_hash="stored-hash-value")
        db.session.add(user)
        db.session.commit()

        assert user.auth_version == 1


@pytest.mark.parametrize("auth_version", [0, -1])
def test_auth_version_database_check_rejects_nonpositive_values(app, auth_version):
    with app.app_context():
        db.session.add(
            User(
                username=f"user{abs(auth_version)}",
                password_hash="stored-hash-value",
                auth_version=auth_version,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_second_migration_exists_with_expected_revision_chain_and_constraint():
    source = SECOND_MIGRATION.read_text(encoding="utf-8")

    assert f'revision = "{SECOND_REVISION}"' in source
    assert f'down_revision = "{FIRST_REVISION}"' in source
    assert "auth_version" in source
    assert "ck_users_auth_version_positive" in source
    assert "batch_alter_table" in source
    assert "drop_constraint" in source
    assert "drop_column" in source


def test_phase_one_migration_is_unchanged_from_preserved_tag():
    tagged = subprocess.run(
        ["git", "show", f"phase-01-foundation:{FIRST_MIGRATION.as_posix()}"],
        check=True,
        capture_output=True,
    ).stdout

    assert FIRST_MIGRATION.read_bytes() == tagged


def test_phase_two_migration_is_unchanged_from_preserved_tag():
    for migration in (FIRST_MIGRATION, SECOND_MIGRATION):
        tagged = subprocess.run(
            ["git", "show", f"phase-02-auth-users:{migration.as_posix()}"],
            check=True,
            capture_output=True,
        ).stdout
        assert migration.read_bytes() == tagged


def test_third_migration_chain_constraints_and_indexes():
    source = THIRD_MIGRATION.read_text(encoding="utf-8")

    assert f'revision = "{THIRD_REVISION}"' in source
    assert f'down_revision = "{SECOND_REVISION}"' in source
    assert "ck_products_price_range" in source
    assert "uq_products_image_filename" in source
    assert "ix_products_public_status_created" in source
    assert "ix_products_seller_status_updated" in source
    assert "ix_products_price" in source


def test_phase_three_migrations_are_unchanged_from_preserved_tag():
    for migration in (FIRST_MIGRATION, SECOND_MIGRATION, THIRD_MIGRATION):
        tagged = subprocess.run(
            ["git", "show", f"phase-03-products-search:{migration.as_posix()}"],
            check=True,
            capture_output=True,
        ).stdout
        assert migration.read_bytes() == tagged


def test_fourth_migration_chain_chat_constraint_and_indexes():
    source = FOURTH_MIGRATION.read_text(encoding="utf-8")

    assert f'revision = "{FOURTH_REVISION}"' in source
    assert f'down_revision = "{THIRD_REVISION}"' in source
    assert "ck_chat_messages_is_hidden_boolean" in source
    assert "ix_chat_messages_conversation_visible_created" in source
    assert "ix_chat_messages_sender_created" in source
    assert "ix_direct_conversations_user1_created" in source
    assert "ix_direct_conversations_user2_created" in source
    assert len(tuple(Path("migrations/versions").glob("*.py"))) == 5


def test_fifth_migration_chain_moderation_constraints_and_indexes():
    source = FIFTH_MIGRATION.read_text(encoding="utf-8")

    assert f'revision = "{FIFTH_REVISION}"' in source
    assert f'down_revision = "{FOURTH_REVISION}"' in source
    assert "ck_products_moderation_previous_status" in source
    assert "ck_reports_review_consistency" in source
    assert "ix_reports_target_status_created" in source
    assert "ix_reports_reporter_created" in source
    assert "ck_audit_logs_action_length" in source
    assert "ck_audit_logs_target_type_length" in source
    assert "ix_audit_logs_created" in source
    assert "ix_audit_logs_actor_created" in source
    assert "ix_audit_logs_target_created" in source


def test_phase_four_migrations_are_unchanged_from_preserved_tag():
    for migration in (
        FIRST_MIGRATION,
        SECOND_MIGRATION,
        THIRD_MIGRATION,
        FOURTH_MIGRATION,
    ):
        tagged = subprocess.run(
            ["git", "show", f"phase-04-chat:{migration.as_posix()}"],
            check=True,
            capture_output=True,
        ).stdout
        assert migration.read_bytes() == tagged


def test_full_migration_upgrade_downgrade_reupgrade_and_drift_check(tmp_path):
    database_path = tmp_path / "migration-check.sqlite"

    upgrade = run_flask(database_path, "db", "upgrade")
    assert_flask_success(upgrade)
    current = run_flask(database_path, "db", "current")
    assert_flask_success(current)
    assert FIFTH_REVISION in current.stdout
    check = run_flask(database_path, "db", "check")
    assert_flask_success(check)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(users)")
        }
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()[0]
    assert columns["auth_version"][3] == 1
    assert str(columns["auth_version"][4]).strip("'\"") == "1"
    assert "ck_users_auth_version_positive" in schema

    downgrade = run_flask(database_path, "db", "downgrade", FOURTH_REVISION)
    assert_flask_success(downgrade)
    with sqlite3.connect(database_path) as connection:
        product_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='products'"
        ).fetchone()[0]
        report_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(reports)")
        }
    assert "moderation_previous_status" not in product_schema
    assert {"reviewed_by_id", "reviewed_at", "updated_at"}.isdisjoint(report_columns)

    reupgrade = run_flask(database_path, "db", "upgrade")
    assert_flask_success(reupgrade)
    final_check = run_flask(database_path, "db", "check")
    assert_flask_success(final_check)

    with sqlite3.connect(database_path) as connection:
        chat_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='chat_messages'"
        ).fetchone()[0]
        chat_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(chat_messages)")
        }
        direct_indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(direct_conversations)")
        }
        foreign_keys = {
            row[2]
            for row in connection.execute("PRAGMA foreign_key_list(chat_messages)")
        }
        product_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='products'"
        ).fetchone()[0]
        report_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='reports'"
        ).fetchone()[0]
        audit_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='audit_logs'"
        ).fetchone()[0]
        report_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(reports)")
        }
        audit_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(audit_logs)")
        }
    assert "ck_chat_messages_body_length" in chat_schema
    assert "ck_chat_messages_is_hidden_boolean" in chat_schema
    assert {
        "ix_chat_messages_conversation_visible_created",
        "ix_chat_messages_sender_created",
    }.issubset(chat_indexes)
    assert {
        "ix_direct_conversations_user1_created",
        "ix_direct_conversations_user2_created",
    }.issubset(direct_indexes)
    assert {"users", "direct_conversations"}.issubset(foreign_keys)
    assert "ck_products_moderation_previous_status" in product_schema
    assert "ck_reports_review_consistency" in report_schema
    assert "ck_audit_logs_action_length" in audit_schema
    assert {
        "ix_reports_target_status_created",
        "ix_reports_reporter_created",
    }.issubset(report_indexes)
    assert {
        "ix_audit_logs_created",
        "ix_audit_logs_actor_created",
        "ix_audit_logs_target_created",
    }.issubset(audit_indexes)

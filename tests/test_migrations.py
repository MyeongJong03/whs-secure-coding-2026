import os
import secrets
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Transfer, User


FIRST_REVISION = "09357cac1cb7"
SECOND_REVISION = "57c21fbc6f83"
THIRD_REVISION = "c3d57de11bfa"
FOURTH_REVISION = "a91f4c8d2e70"
FIFTH_REVISION = "e5b7a2c9d4f1"
SIXTH_REVISION = "f8c2d1e7a6b4"
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
SIXTH_MIGRATION = Path(
    "migrations/versions/f8c2d1e7a6b4_add_secure_transfer_constraints_and_indexes.py"
)
PROTECTED_MIGRATIONS = (
    FIRST_MIGRATION,
    SECOND_MIGRATION,
    THIRD_MIGRATION,
    FOURTH_MIGRATION,
    FIFTH_MIGRATION,
)
SENDER_ID = "00000000-0000-0000-0000-000000000001"
RECIPIENT_ID = "00000000-0000-0000-0000-000000000002"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000003"
CREATED_AT = "2026-07-24 00:00:00.000000"


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


@pytest.fixture
def migrated_database_path(tmp_path):
    database_path = tmp_path / "transfer-constraints.sqlite"
    assert_flask_success(run_flask(database_path, "db", "upgrade"))
    return database_path


def seed_transfer_users(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executemany(
        """
        INSERT INTO users (
            id, username, password_hash, bio, role, status, auth_version,
            created_at, updated_at
        )
        VALUES (?, ?, ?, '', 'user', 'active', 1, ?, ?)
        """,
        (
            (SENDER_ID, "sender", "stored-hash-value", CREATED_AT, CREATED_AT),
            (
                RECIPIENT_ID,
                "recipient",
                "stored-hash-value",
                CREATED_AT,
                CREATED_AT,
            ),
            (
                OTHER_USER_ID,
                "otheruser",
                "stored-hash-value",
                CREATED_AT,
                CREATED_AT,
            ),
        ),
    )
    connection.commit()


def insert_transfer(
    connection: sqlite3.Connection,
    *,
    transfer_id: str,
    amount: int,
    idempotency_key: str,
    sender_id: str = SENDER_ID,
    recipient_id: str = RECIPIENT_ID,
) -> None:
    connection.execute(
        """
        INSERT INTO transfers (
            id, sender_id, recipient_id, amount, idempotency_key, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            transfer_id,
            sender_id,
            recipient_id,
            amount,
            idempotency_key,
            CREATED_AT,
        ),
    )


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


def test_sixth_migration_chain_transfer_constraints_indexes_and_downgrade():
    source = SIXTH_MIGRATION.read_text(encoding="utf-8")

    assert f'revision = "{SIXTH_REVISION}"' in source
    assert f'down_revision = "{FIFTH_REVISION}"' in source
    assert "ck_transfers_amount_positive" in source
    assert "ck_transfers_amount_range" in source
    assert "amount BETWEEN 1 AND 1000000000" in source
    assert "ck_transfers_idempotency_key_format" in source
    assert "length(idempotency_key) = 64" in source
    assert "idempotency_key NOT GLOB '*[^0-9a-f]*'" in source
    assert "ix_transfers_sender_created" in source
    assert "ix_transfers_recipient_created" in source
    assert "drop_index" in source
    assert "drop_constraint" in source
    assert len(tuple(Path("migrations/versions").glob("*.py"))) == 6


def test_phase_five_migrations_are_unchanged_from_preserved_tag():
    for migration in PROTECTED_MIGRATIONS:
        tagged = subprocess.run(
            [
                "git",
                "show",
                f"phase-05-moderation-admin:{migration.as_posix()}",
            ],
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
    assert SIXTH_REVISION in current.stdout
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

    downgrade = run_flask(database_path, "db", "downgrade", FIFTH_REVISION)
    assert_flask_success(downgrade)
    with sqlite3.connect(database_path) as connection:
        product_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='products'"
        ).fetchone()[0]
        report_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(reports)")
        }
        downgraded_transfer_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='transfers'"
        ).fetchone()[0]
        downgraded_transfer_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(transfers)")
        }
    assert "moderation_previous_status" in product_schema
    assert {"reviewed_by_id", "reviewed_at", "updated_at"}.issubset(report_columns)
    assert "ck_transfers_amount_positive" in downgraded_transfer_schema
    assert "ck_transfers_amount_range" not in downgraded_transfer_schema
    assert "ck_transfers_idempotency_key_format" not in downgraded_transfer_schema
    assert "ix_transfers_sender_created" not in downgraded_transfer_indexes
    assert "ix_transfers_recipient_created" not in downgraded_transfer_indexes

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
        transfer_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='transfers'"
        ).fetchone()[0]
        transfer_index_rows = tuple(connection.execute("PRAGMA index_list(transfers)"))
        transfer_indexes = {row[1] for row in transfer_index_rows}
        transfer_index_columns = {
            name: tuple(
                row[2] for row in connection.execute(f"PRAGMA index_info('{name}')")
            )
            for name in (
                "ix_transfers_sender_created",
                "ix_transfers_recipient_created",
            )
        }
        transfer_foreign_keys = {
            (row[3], row[2], row[4], row[6])
            for row in connection.execute("PRAGMA foreign_key_list(transfers)")
        }
        transfer_unique_indexes = {
            tuple(
                index_row[2]
                for index_row in connection.execute(f"PRAGMA index_info('{row[1]}')")
            )
            for row in transfer_index_rows
            if row[2] == 1
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
    assert "ck_transfers_amount_range" in transfer_schema
    assert "ck_transfers_idempotency_key_format" in transfer_schema
    assert "ck_transfers_distinct_users" in transfer_schema
    assert "ck_transfers_amount_positive" not in transfer_schema
    assert {
        "ix_transfers_sender_created",
        "ix_transfers_recipient_created",
    }.issubset(transfer_indexes)
    assert transfer_index_columns == {
        "ix_transfers_sender_created": ("sender_id", "created_at", "id"),
        "ix_transfers_recipient_created": ("recipient_id", "created_at", "id"),
    }
    assert transfer_foreign_keys == {
        ("sender_id", "users", "id", "RESTRICT"),
        ("recipient_id", "users", "id", "RESTRICT"),
    }
    assert ("idempotency_key",) in transfer_unique_indexes

    model_check_names = {
        constraint.name
        for constraint in Transfer.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert model_check_names == {
        "ck_transfers_amount_range",
        "ck_transfers_idempotency_key_format",
        "ck_transfers_distinct_users",
    }
    assert {
        index.name: tuple(column.name for column in index.columns)
        for index in Transfer.__table__.indexes
    } == transfer_index_columns


def test_migrated_transfer_amount_check_rejects_out_of_range_values(
    migrated_database_path,
):
    with sqlite3.connect(migrated_database_path) as connection:
        seed_transfer_users(connection)
        for index, amount in enumerate((0, -1, 1_000_000_001), start=1):
            with pytest.raises(sqlite3.IntegrityError):
                insert_transfer(
                    connection,
                    transfer_id=f"{index:036d}",
                    amount=amount,
                    idempotency_key=f"{index:064x}",
                )

        assert connection.execute("SELECT count(*) FROM transfers").fetchone()[0] == 0


def test_migrated_transfer_amount_check_accepts_boundaries(
    migrated_database_path,
):
    with sqlite3.connect(migrated_database_path) as connection:
        seed_transfer_users(connection)
        for index, amount in enumerate((1, 1_000_000_000), start=1):
            insert_transfer(
                connection,
                transfer_id=f"{index:036d}",
                amount=amount,
                idempotency_key=f"{index:064x}",
            )
        connection.commit()

        assert connection.execute(
            "SELECT amount FROM transfers ORDER BY amount"
        ).fetchall() == [(1,), (1_000_000_000,)]


def test_migrated_transfer_idempotency_format_rejects_invalid_keys(
    migrated_database_path,
):
    invalid_keys = (
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
    )
    with sqlite3.connect(migrated_database_path) as connection:
        seed_transfer_users(connection)
        for index, idempotency_key in enumerate(invalid_keys, start=1):
            with pytest.raises(sqlite3.IntegrityError):
                insert_transfer(
                    connection,
                    transfer_id=f"{index:036d}",
                    amount=1,
                    idempotency_key=idempotency_key,
                )

        assert connection.execute("SELECT count(*) FROM transfers").fetchone()[0] == 0


def test_migrated_transfer_idempotency_format_accepts_lowercase_hex(
    migrated_database_path,
):
    idempotency_key = "0123456789abcdef" * 4
    with sqlite3.connect(migrated_database_path) as connection:
        seed_transfer_users(connection)
        insert_transfer(
            connection,
            transfer_id="1" * 36,
            amount=1,
            idempotency_key=idempotency_key,
        )
        connection.commit()

        stored = connection.execute("SELECT idempotency_key FROM transfers").fetchone()[
            0
        ]
        assert stored == idempotency_key


def test_migrated_transfer_preserves_unique_distinct_and_foreign_keys(
    migrated_database_path,
):
    idempotency_key = "b" * 64
    with sqlite3.connect(migrated_database_path) as connection:
        seed_transfer_users(connection)
        insert_transfer(
            connection,
            transfer_id="1" * 36,
            amount=1,
            idempotency_key=idempotency_key,
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            insert_transfer(
                connection,
                transfer_id="2" * 36,
                amount=1,
                idempotency_key=idempotency_key,
                recipient_id=OTHER_USER_ID,
            )
        with pytest.raises(sqlite3.IntegrityError):
            insert_transfer(
                connection,
                transfer_id="3" * 36,
                amount=1,
                idempotency_key="c" * 64,
                recipient_id=SENDER_ID,
            )
        with pytest.raises(sqlite3.IntegrityError):
            insert_transfer(
                connection,
                transfer_id="4" * 36,
                amount=1,
                idempotency_key="d" * 64,
                sender_id="missing-sender",
            )
        with pytest.raises(sqlite3.IntegrityError):
            insert_transfer(
                connection,
                transfer_id="5" * 36,
                amount=1,
                idempotency_key="e" * 64,
                recipient_id="missing-recipient",
            )

        assert connection.execute("SELECT count(*) FROM transfers").fetchone()[0] == 1

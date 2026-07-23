import click
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.audit.services import add_audit_log
from app.auth.forms import USERNAME_PATTERN
from app.extensions import db
from app.models import User, Wallet


def _valid_username(username: str) -> bool:
    return 4 <= len(username) <= 32 and USERNAME_PATTERN.fullmatch(username) is not None


@click.command("create-admin")
@click.option("--username", required=True, metavar="ADMIN_USERNAME")
@with_appcontext
def create_admin(username: str) -> None:
    normalized_username = username.strip()
    if not _valid_username(normalized_username):
        raise click.ClickException("Invalid admin username.")
    if (
        db.session.execute(
            db.select(User.id).where(User.username == normalized_username)
        ).scalar_one_or_none()
        is not None
    ):
        raise click.ClickException("Admin username is unavailable.")

    password = click.prompt("Password", hide_input=True, show_default=False)
    confirmation = click.prompt("Confirm password", hide_input=True, show_default=False)
    if password != confirmation:
        raise click.ClickException("Password confirmation does not match.")
    if not 12 <= len(password) <= 128:
        raise click.ClickException("Password must be between 12 and 128 characters.")

    admin = User(
        username=normalized_username,
        role="admin",
        status="active",
        auth_version=1,
    )
    admin.set_password(password)
    wallet = Wallet(user=admin, balance=100000)
    db.session.add_all((admin, wallet))
    try:
        db.session.flush()
        add_audit_log(
            actor_user_id=None,
            action="admin.account_created",
            target_type="user",
            target_id=admin.id,
            details={"username": normalized_username},
        )
        db.session.commit()
    except (IntegrityError, SQLAlchemyError, ValueError):
        db.session.rollback()
        raise click.ClickException("Admin account creation failed.") from None
    click.echo(f"Admin account created: {normalized_username}")


def register_cli(app) -> None:
    app.cli.add_command(create_admin)

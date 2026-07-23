from enum import Enum, auto

from flask import current_app
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash

from app.extensions import db
from app.models import User, Wallet


class RegistrationResult(Enum):
    CREATED = auto()
    DUPLICATE_USERNAME = auto()
    DATABASE_ERROR = auto()


def register_user(username: str, password: str) -> RegistrationResult:
    existing_user = db.session.execute(
        db.select(User.id).where(User.username == username)
    ).scalar_one_or_none()
    if existing_user is not None:
        return RegistrationResult.DUPLICATE_USERNAME

    user = User(
        username=username,
        role="user",
        status="active",
        auth_version=1,
    )
    user.set_password(password)
    wallet = Wallet(user=user, balance=100000)
    db.session.add_all((user, wallet))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return RegistrationResult.DUPLICATE_USERNAME
    except SQLAlchemyError:
        db.session.rollback()
        return RegistrationResult.DATABASE_ERROR
    return RegistrationResult.CREATED


def authenticate_user(username: str, password: str) -> User | None:
    user = db.session.execute(
        db.select(User).where(User.username == username)
    ).scalar_one_or_none()
    if user is None or user.status != "active":
        check_password_hash(current_app.extensions["auth_dummy_hash"], password)
        return None
    if not user.check_password(password):
        return None
    return user

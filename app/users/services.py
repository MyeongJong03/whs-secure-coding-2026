from dataclasses import dataclass
from enum import Enum, auto
from math import ceil

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import User


@dataclass(frozen=True, slots=True)
class PublicUserView:
    username: str
    bio: str


@dataclass(frozen=True, slots=True)
class PublicUserPage:
    items: tuple[PublicUserView, ...]
    page: int
    per_page: int
    total: int
    pages: int

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def prev_num(self) -> int | None:
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self) -> int | None:
        return self.page + 1 if self.has_next else None


class PasswordChangeResult(Enum):
    CHANGED = auto()
    CURRENT_PASSWORD_INVALID = auto()
    PASSWORD_UNCHANGED = auto()
    DATABASE_ERROR = auto()


def search_public_users(query: str | None, page: int, per_page: int) -> PublicUserPage:
    limited_per_page = min(max(per_page, 1), 20)
    filters = [User.status == "active"]
    if query:
        filters.append(User.username.contains(query, autoescape=True))

    total = db.session.execute(
        db.select(func.count()).select_from(User).where(*filters)
    ).scalar_one()
    statement = (
        db.select(User.username, User.bio)
        .where(*filters)
        .order_by(User.username.asc(), User.id.asc())
        .limit(limited_per_page)
        .offset((page - 1) * limited_per_page)
    )
    items = tuple(
        PublicUserView(username=username, bio=bio)
        for username, bio in db.session.execute(statement)
    )
    return PublicUserPage(
        items=items,
        page=page,
        per_page=limited_per_page,
        total=total,
        pages=ceil(total / limited_per_page),
    )


def get_public_user(username: str) -> PublicUserView | None:
    row = db.session.execute(
        db.select(User.username, User.bio).where(
            User.username == username,
            User.status == "active",
        )
    ).one_or_none()
    if row is None:
        return None
    return PublicUserView(username=row.username, bio=row.bio)


def update_bio(user: User, bio: str) -> bool:
    user.bio = bio
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return False
    return True


def change_password(
    user: User, current_password: str, new_password: str
) -> PasswordChangeResult:
    if not user.check_password(current_password):
        return PasswordChangeResult.CURRENT_PASSWORD_INVALID
    if user.check_password(new_password):
        return PasswordChangeResult.PASSWORD_UNCHANGED

    user.set_password(new_password)
    user.auth_version += 1
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return PasswordChangeResult.DATABASE_ERROR
    return PasswordChangeResult.CHANGED

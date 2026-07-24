from dataclasses import dataclass
from enum import Enum, auto
from math import ceil

from flask import current_app
from sqlalchemy import case, func, or_, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import aliased
from werkzeug.security import check_password_hash

from app.audit.services import add_audit_log
from app.extensions import db
from app.models import Transfer, User, Wallet
from app.wallet.policy import (
    derive_idempotency_key,
    normalize_recipient_username,
    valid_idempotency_token,
)
from app.wallet.views import (
    TransferDetailView,
    TransferHistoryPage,
    TransferHistoryView,
    WalletSummaryView,
)


class TransferResult(Enum):
    CREATED = auto()
    IDEMPOTENT = auto()
    IDEMPOTENCY_CONFLICT = auto()
    SELF_TRANSFER = auto()
    RECIPIENT_UNAVAILABLE = auto()
    CURRENT_PASSWORD_INVALID = auto()
    INSUFFICIENT_FUNDS = auto()
    DATABASE_ERROR = auto()


@dataclass(frozen=True, slots=True)
class TransferOutcome:
    result: TransferResult
    transfer_id: str | None = None


def _rollback_outcome(
    result: TransferResult, transfer_id: str | None = None
) -> TransferOutcome:
    db.session.rollback()
    return TransferOutcome(result, transfer_id)


def _begin_write_transaction() -> None:
    db.session.rollback()
    if db.session.get_bind().dialect.name == "sqlite":
        db.session.execute(text("BEGIN IMMEDIATE"))
    else:
        db.session.begin()


def _existing_transfer(idempotency_key: str):
    return db.session.execute(
        db.select(
            Transfer.id,
            Transfer.sender_id,
            Transfer.recipient_id,
            Transfer.amount,
        ).where(Transfer.idempotency_key == idempotency_key)
    ).one_or_none()


def _resolve_existing(
    *,
    idempotency_key: str,
    sender_id: str,
    recipient_id: str,
    amount: int,
) -> TransferOutcome | None:
    existing = _existing_transfer(idempotency_key)
    if existing is None:
        return None
    if (
        existing.sender_id == sender_id
        and existing.recipient_id == recipient_id
        and existing.amount == amount
    ):
        return TransferOutcome(TransferResult.IDEMPOTENT, existing.id)
    return TransferOutcome(TransferResult.IDEMPOTENCY_CONFLICT)


def _debit_sender(sender_id: str, amount: int) -> int:
    active_sender = (
        db.select(User.id).where(User.id == sender_id, User.status == "active").exists()
    )
    result = db.session.execute(
        update(Wallet)
        .where(
            Wallet.user_id == sender_id,
            Wallet.balance >= amount,
            active_sender,
        )
        .values(balance=Wallet.balance - amount)
    )
    return result.rowcount


def _credit_recipient(recipient_id: str, amount: int) -> int:
    active_recipient = (
        db.select(User.id)
        .where(User.id == recipient_id, User.status == "active")
        .exists()
    )
    result = db.session.execute(
        update(Wallet)
        .where(Wallet.user_id == recipient_id, active_recipient)
        .values(balance=Wallet.balance + amount)
    )
    return result.rowcount


def create_transfer(
    *,
    sender_id: str,
    recipient_username: object,
    amount: object,
    current_password: object,
    raw_idempotency_token: object,
) -> TransferOutcome:
    normalized_recipient = normalize_recipient_username(recipient_username)
    if normalized_recipient is None:
        return TransferOutcome(TransferResult.RECIPIENT_UNAVAILABLE)
    if (
        not isinstance(amount, int)
        or isinstance(amount, bool)
        or not current_app.config["TRANSFER_MIN_AMOUNT"]
        <= amount
        <= current_app.config["TRANSFER_MAX_AMOUNT"]
    ):
        return TransferOutcome(TransferResult.DATABASE_ERROR)
    if not isinstance(current_password, str) or not 1 <= len(current_password) <= 128:
        return TransferOutcome(TransferResult.CURRENT_PASSWORD_INVALID)
    if not valid_idempotency_token(raw_idempotency_token):
        return TransferOutcome(TransferResult.DATABASE_ERROR)
    if not isinstance(sender_id, str) or not sender_id:
        return TransferOutcome(TransferResult.CURRENT_PASSWORD_INVALID)

    idempotency_key = derive_idempotency_key(sender_id, raw_idempotency_token)
    recipient_id: str | None = None
    try:
        _begin_write_transaction()
        sender = db.session.execute(
            db.select(User.id, User.password_hash).where(
                User.id == sender_id,
                User.status == "active",
            )
        ).one_or_none()
        if sender is None or not check_password_hash(
            sender.password_hash, current_password
        ):
            return _rollback_outcome(TransferResult.CURRENT_PASSWORD_INVALID)

        recipient = db.session.execute(
            db.select(User.id, User.status).where(
                User.username == normalized_recipient,
            )
        ).one_or_none()
        if recipient is None:
            return _rollback_outcome(TransferResult.RECIPIENT_UNAVAILABLE)
        recipient_id = recipient.id

        existing = _resolve_existing(
            idempotency_key=idempotency_key,
            sender_id=sender_id,
            recipient_id=recipient_id,
            amount=amount,
        )
        if existing is not None:
            return _rollback_outcome(existing.result, existing.transfer_id)
        if recipient_id == sender_id:
            return _rollback_outcome(TransferResult.SELF_TRANSFER)
        if recipient.status != "active":
            return _rollback_outcome(TransferResult.RECIPIENT_UNAVAILABLE)

        sender_wallet_exists = db.session.execute(
            db.select(Wallet.user_id).where(Wallet.user_id == sender_id)
        ).scalar_one_or_none()
        if sender_wallet_exists is None:
            return _rollback_outcome(TransferResult.DATABASE_ERROR)
        recipient_wallet_exists = db.session.execute(
            db.select(Wallet.user_id).where(Wallet.user_id == recipient_id)
        ).scalar_one_or_none()
        if recipient_wallet_exists is None:
            return _rollback_outcome(TransferResult.RECIPIENT_UNAVAILABLE)

        transfer = Transfer(
            sender_id=sender_id,
            recipient_id=recipient_id,
            amount=amount,
            idempotency_key=idempotency_key,
        )
        db.session.add(transfer)
        db.session.flush()

        if _debit_sender(sender_id, amount) != 1:
            return _rollback_outcome(TransferResult.INSUFFICIENT_FUNDS)
        if _credit_recipient(recipient_id, amount) != 1:
            return _rollback_outcome(TransferResult.RECIPIENT_UNAVAILABLE)

        add_audit_log(
            actor_user_id=sender_id,
            action="transfer.created",
            target_type="transfer",
            target_id=transfer.id,
            details={"amount": amount},
        )
        transfer_id = transfer.id
        db.session.commit()
        return TransferOutcome(TransferResult.CREATED, transfer_id)
    except IntegrityError:
        db.session.rollback()
        if recipient_id is None:
            return TransferOutcome(TransferResult.DATABASE_ERROR)
        try:
            existing = _resolve_existing(
                idempotency_key=idempotency_key,
                sender_id=sender_id,
                recipient_id=recipient_id,
                amount=amount,
            )
        except SQLAlchemyError:
            db.session.rollback()
            return TransferOutcome(TransferResult.DATABASE_ERROR)
        return existing or TransferOutcome(TransferResult.DATABASE_ERROR)
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        return TransferOutcome(TransferResult.DATABASE_ERROR)


def get_wallet_summary(user_id: str) -> WalletSummaryView | None:
    row = db.session.execute(
        db.select(User.username, Wallet.balance)
        .join(Wallet, Wallet.user_id == User.id)
        .where(User.id == user_id, User.status == "active")
    ).one_or_none()
    if row is None:
        return None
    return WalletSummaryView(username=row.username, balance=row.balance)


def list_transfer_history(
    *,
    user_id: str,
    direction: str,
    sort: str,
    page: int,
    per_page: int,
) -> TransferHistoryPage:
    sender = aliased(User)
    recipient = aliased(User)
    filters = [or_(Transfer.sender_id == user_id, Transfer.recipient_id == user_id)]
    if direction == "sent":
        filters.append(Transfer.sender_id == user_id)
    elif direction == "received":
        filters.append(Transfer.recipient_id == user_id)

    order = (
        (Transfer.created_at.asc(), Transfer.id.asc())
        if sort == "oldest"
        else (Transfer.created_at.desc(), Transfer.id.desc())
    )
    total = db.session.execute(
        db.select(func.count()).select_from(Transfer).where(*filters)
    ).scalar_one()
    rows = db.session.execute(
        db.select(
            Transfer.id,
            case((Transfer.sender_id == user_id, "sent"), else_="received").label(
                "direction"
            ),
            case(
                (Transfer.sender_id == user_id, recipient.username),
                else_=sender.username,
            ).label("counterpart_username"),
            Transfer.amount,
            Transfer.created_at,
        )
        .select_from(Transfer)
        .join(sender, Transfer.sender_id == sender.id)
        .join(recipient, Transfer.recipient_id == recipient.id)
        .where(*filters)
        .order_by(*order)
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    items = tuple(
        TransferHistoryView(
            id=row.id,
            direction=row.direction,
            counterpart_username=row.counterpart_username,
            amount=row.amount,
            created_at=row.created_at,
        )
        for row in rows
    )
    pages = ceil(total / per_page)
    return TransferHistoryPage(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        pages=pages,
        has_prev=page > 1,
        has_next=page < pages,
        prev_num=page - 1 if page > 1 else None,
        next_num=page + 1 if page < pages else None,
    )


def get_transfer_detail(*, user_id: str, transfer_id: str) -> TransferDetailView | None:
    sender = aliased(User)
    recipient = aliased(User)
    row = db.session.execute(
        db.select(
            Transfer.id,
            sender.username.label("sender_username"),
            recipient.username.label("recipient_username"),
            case((Transfer.sender_id == user_id, "sent"), else_="received").label(
                "direction"
            ),
            Transfer.amount,
            Transfer.created_at,
        )
        .select_from(Transfer)
        .join(sender, Transfer.sender_id == sender.id)
        .join(recipient, Transfer.recipient_id == recipient.id)
        .where(
            Transfer.id == transfer_id,
            or_(
                Transfer.sender_id == user_id,
                Transfer.recipient_id == user_id,
            ),
        )
    ).one_or_none()
    if row is None:
        return None
    return TransferDetailView(
        id=row.id,
        sender_username=row.sender_username,
        recipient_username=row.recipient_username,
        direction=row.direction,
        amount=row.amount,
        created_at=row.created_at,
    )

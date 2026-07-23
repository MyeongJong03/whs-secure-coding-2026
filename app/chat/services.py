from datetime import datetime, timezone
from enum import Enum, auto
from math import ceil

from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import aliased

from app.chat.views import (
    ChatMessagePage,
    ChatMessageView,
    DirectConversationPage,
    DirectConversationSummary,
    DirectConversationView,
)
from app.extensions import db
from app.models import ChatMessage, DirectConversation, User, utc_now


class DirectConversationResult(Enum):
    CREATED = auto()
    EXISTING = auto()
    TARGET_UNAVAILABLE = auto()
    SELF_TARGET = auto()
    DATABASE_ERROR = auto()


class MessageSaveResult(Enum):
    SAVED = auto()
    DATABASE_ERROR = auto()


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def start_direct_conversation(
    authenticated_user: User, target_username: str
) -> tuple[DirectConversationResult, str | None]:
    if hasattr(authenticated_user, "_get_current_object"):
        authenticated_user = authenticated_user._get_current_object()
    current_row = db.session.execute(
        db.select(User.id, User.status).where(User.id == authenticated_user.id)
    ).one_or_none()
    target_row = db.session.execute(
        db.select(User.id).where(
            User.username == target_username,
            User.status == "active",
        )
    ).one_or_none()
    if current_row is None or current_row.status != "active" or target_row is None:
        return DirectConversationResult.TARGET_UNAVAILABLE, None
    if current_row.id == target_row.id:
        return DirectConversationResult.SELF_TARGET, None

    user1_id, user2_id = sorted((current_row.id, target_row.id))
    existing = db.session.execute(
        db.select(DirectConversation.id).where(
            DirectConversation.user1_id == user1_id,
            DirectConversation.user2_id == user2_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return DirectConversationResult.EXISTING, existing

    conversation = DirectConversation(user1_id=user1_id, user2_id=user2_id)
    db.session.add(conversation)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = db.session.execute(
            db.select(DirectConversation.id).where(
                DirectConversation.user1_id == user1_id,
                DirectConversation.user2_id == user2_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return DirectConversationResult.EXISTING, existing
        return DirectConversationResult.DATABASE_ERROR, None
    except SQLAlchemyError:
        db.session.rollback()
        return DirectConversationResult.DATABASE_ERROR, None
    return DirectConversationResult.CREATED, conversation.id


def get_message_history(
    *,
    conversation_id: str | None,
    page: int,
    per_page: int,
) -> ChatMessagePage:
    scope_filter = (
        ChatMessage.conversation_id.is_(None)
        if conversation_id is None
        else ChatMessage.conversation_id == conversation_id
    )
    filters = (scope_filter, ChatMessage.is_hidden.is_(False))
    total = db.session.execute(
        db.select(func.count()).select_from(ChatMessage).where(*filters)
    ).scalar_one()
    statement = (
        db.select(
            ChatMessage.id,
            User.username,
            ChatMessage.body,
            ChatMessage.created_at,
        )
        .select_from(ChatMessage)
        .join(User, ChatMessage.sender_id == User.id)
        .where(*filters)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    newest_first = tuple(db.session.execute(statement))
    items = tuple(
        ChatMessageView(
            id=row.id,
            sender_username=row.username,
            body=row.body,
            created_at_iso=_iso_utc(row.created_at),
        )
        for row in reversed(newest_first)
    )
    pages = ceil(total / per_page)
    has_prev = page > 1
    has_next = page < pages
    return ChatMessagePage(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        pages=pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_num=page - 1 if has_prev else None,
        next_num=page + 1 if has_next else None,
    )


def list_direct_conversations(
    *, user_id: str, page: int, per_page: int
) -> DirectConversationPage:
    counterpart = aliased(User)
    participant_filter = or_(
        DirectConversation.user1_id == user_id,
        DirectConversation.user2_id == user_id,
    )
    counterpart_join = or_(
        and_(
            DirectConversation.user1_id == user_id,
            counterpart.id == DirectConversation.user2_id,
        ),
        and_(
            DirectConversation.user2_id == user_id,
            counterpart.id == DirectConversation.user1_id,
        ),
    )
    total = db.session.execute(
        db.select(func.count())
        .select_from(DirectConversation)
        .where(participant_filter)
    ).scalar_one()
    statement = (
        db.select(
            DirectConversation.id,
            counterpart.username,
            case((counterpart.status == "active", True), else_=False).label(
                "counterpart_is_active"
            ),
            DirectConversation.created_at,
        )
        .select_from(DirectConversation)
        .join(counterpart, counterpart_join)
        .where(participant_filter)
        .order_by(DirectConversation.created_at.desc(), DirectConversation.id.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    items = tuple(
        DirectConversationSummary(
            id=row.id,
            counterpart_username=row.username,
            counterpart_is_active=bool(row.counterpart_is_active),
            created_at_iso=_iso_utc(row.created_at),
        )
        for row in db.session.execute(statement)
    )
    pages = ceil(total / per_page)
    has_prev = page > 1
    has_next = page < pages
    return DirectConversationPage(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        pages=pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_num=page - 1 if has_prev else None,
        next_num=page + 1 if has_next else None,
    )


def get_direct_conversation(
    conversation_id: str, user_id: str
) -> DirectConversationView | None:
    counterpart = aliased(User)
    participant_filter = or_(
        DirectConversation.user1_id == user_id,
        DirectConversation.user2_id == user_id,
    )
    counterpart_join = or_(
        and_(
            DirectConversation.user1_id == user_id,
            counterpart.id == DirectConversation.user2_id,
        ),
        and_(
            DirectConversation.user2_id == user_id,
            counterpart.id == DirectConversation.user1_id,
        ),
    )
    row = db.session.execute(
        db.select(
            DirectConversation.id,
            counterpart.username,
            case((counterpart.status == "active", True), else_=False).label(
                "counterpart_is_active"
            ),
        )
        .select_from(DirectConversation)
        .join(counterpart, counterpart_join)
        .where(
            DirectConversation.id == conversation_id,
            participant_filter,
        )
    ).one_or_none()
    if row is None:
        return None
    return DirectConversationView(
        id=row.id,
        counterpart_username=row.username,
        counterpart_is_active=bool(row.counterpart_is_active),
    )


def save_message(
    *, sender_id: str, conversation_id: str | None, body: str
) -> tuple[MessageSaveResult, ChatMessageView | None]:
    sender_username = db.session.execute(
        db.select(User.username).where(
            User.id == sender_id,
            User.status == "active",
        )
    ).scalar_one_or_none()
    if sender_username is None:
        return MessageSaveResult.DATABASE_ERROR, None

    created_at = utc_now()
    message = ChatMessage(
        sender_id=sender_id,
        conversation_id=conversation_id,
        body=body,
        is_hidden=False,
        created_at=created_at,
    )
    db.session.add(message)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return MessageSaveResult.DATABASE_ERROR, None
    return (
        MessageSaveResult.SAVED,
        ChatMessageView(
            id=message.id,
            sender_username=sender_username,
            body=body,
            created_at_iso=_iso_utc(created_at),
        ),
    )


def message_payload(message: ChatMessageView) -> dict[str, str]:
    return {
        "id": message.id,
        "sender_username": message.sender_username,
        "body": message.body,
        "created_at_iso": message.created_at_iso,
    }

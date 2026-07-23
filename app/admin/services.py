from enum import Enum, auto
from math import ceil

from sqlalchemy import case, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased

from app.admin.views import (
    AdminAuditLogPage,
    AdminAuditLogView,
    AdminMessagePage,
    AdminMessageView,
    AdminProductPage,
    AdminProductSummary,
    AdminProductView,
    AdminReportPage,
    AdminReportSummary,
    AdminReportView,
    AdminTransferPage,
    AdminTransferView,
    AdminUserPage,
    AdminUserSummary,
    AdminUserView,
)
from app.audit.policy import safe_details_for_display
from app.audit.services import add_audit_log
from app.extensions import db
from app.models import (
    AuditLog,
    ChatMessage,
    Product,
    Report,
    Transfer,
    User,
    utc_now,
)


class AdminMutationResult(Enum):
    OK = auto()
    IDEMPOTENT = auto()
    NOT_FOUND = auto()
    INVALID_STATE = auto()
    SELF_PROTECTED = auto()
    LAST_ADMIN = auto()
    DATABASE_ERROR = auto()


def verify_current_password(admin_user: User, password: str) -> bool:
    if hasattr(admin_user, "_get_current_object"):
        admin_user = admin_user._get_current_object()
    return admin_user.check_password(password)


def dashboard_counts() -> dict[str, int]:
    return {
        "users": db.session.execute(
            db.select(func.count()).select_from(User)
        ).scalar_one(),
        "products": db.session.execute(
            db.select(func.count()).select_from(Product)
        ).scalar_one(),
        "pending_reports": db.session.execute(
            db.select(func.count())
            .select_from(Report)
            .where(Report.status == "pending")
        ).scalar_one(),
        "messages": db.session.execute(
            db.select(func.count()).select_from(ChatMessage)
        ).scalar_one(),
    }


def _pages(total: int, per_page: int) -> int:
    return ceil(total / per_page)


def list_users(
    *,
    query: str | None,
    role: str,
    status: str,
    sort: str,
    page: int,
    per_page: int,
) -> AdminUserPage:
    filters = []
    if query:
        filters.append(User.username.contains(query, autoescape=True))
    if role in {"user", "admin"}:
        filters.append(User.role == role)
    if status in {"active", "dormant"}:
        filters.append(User.status == status)
    order = (
        (User.created_at.asc(), User.id.asc())
        if sort == "oldest"
        else (User.created_at.desc(), User.id.desc())
    )
    total = db.session.execute(
        db.select(func.count()).select_from(User).where(*filters)
    ).scalar_one()
    items = tuple(
        AdminUserSummary(
            username=row.username,
            role=row.role,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in db.session.execute(
            db.select(
                User.username,
                User.role,
                User.status,
                User.created_at,
                User.updated_at,
            )
            .where(*filters)
            .order_by(*order)
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    )
    return AdminUserPage(items, page, per_page, total, _pages(total, per_page))


def get_user(username: str) -> AdminUserView | None:
    row = db.session.execute(
        db.select(
            User.username,
            User.role,
            User.status,
            User.created_at,
            User.updated_at,
        ).where(User.username == username)
    ).one_or_none()
    if row is None:
        return None
    return AdminUserView(
        username=row.username,
        role=row.role,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def change_user_status(
    *, actor_id: str, target_username: str, new_status: str
) -> AdminMutationResult:
    if new_status not in {"active", "dormant"}:
        return AdminMutationResult.INVALID_STATE
    target = db.session.execute(
        db.select(User).where(User.username == target_username)
    ).scalar_one_or_none()
    if target is None:
        return AdminMutationResult.NOT_FOUND
    if new_status == "dormant" and target.id == actor_id:
        return AdminMutationResult.SELF_PROTECTED
    if new_status == "dormant" and target.role == "admin" and target.status == "active":
        other_active_admins = db.session.execute(
            db.select(func.count())
            .select_from(User)
            .where(
                User.role == "admin",
                User.status == "active",
                User.id != target.id,
            )
        ).scalar_one()
        if other_active_admins < 1:
            return AdminMutationResult.LAST_ADMIN

    previous = target.status
    changed = previous != new_status
    if changed:
        target.status = new_status
        target.auth_version += 1
    action = f"admin.user.{new_status}"
    try:
        add_audit_log(
            actor_user_id=actor_id,
            action=action,
            target_type="user",
            target_id=target.id,
            details={"previous_status": previous, "new_status": new_status},
        )
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        return AdminMutationResult.DATABASE_ERROR
    if changed:
        from app.chat.connections import disconnect_user_sockets

        disconnect_user_sockets(target.id)
        return AdminMutationResult.OK
    return AdminMutationResult.IDEMPOTENT


def _restore_status(previous: str | None, status: str) -> str | None:
    if status != "hidden":
        return None
    return previous if previous in {"active", "sold"} else "active"


def list_products(
    *,
    query: str | None,
    status: str,
    sort: str,
    page: int,
    per_page: int,
) -> AdminProductPage:
    filters = []
    if query:
        filters.append(
            Product.title.contains(query, autoescape=True)
            | User.username.contains(query, autoescape=True)
        )
    if status in {"active", "sold", "hidden", "deleted"}:
        filters.append(Product.status == status)
    order = (
        (Product.created_at.asc(), Product.id.asc())
        if sort == "oldest"
        else (Product.created_at.desc(), Product.id.desc())
    )
    total = db.session.execute(
        db.select(func.count())
        .select_from(Product)
        .join(User, Product.seller_id == User.id)
        .where(*filters)
    ).scalar_one()
    rows = db.session.execute(
        db.select(
            Product.id,
            Product.title,
            User.username,
            Product.price,
            Product.status,
            Product.moderation_previous_status,
            Product.created_at,
            Product.updated_at,
        )
        .select_from(Product)
        .join(User, Product.seller_id == User.id)
        .where(*filters)
        .order_by(*order)
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    items = tuple(
        AdminProductSummary(
            id=row.id,
            title=row.title,
            seller_username=row.username,
            price=row.price,
            status=row.status,
            restore_status=_restore_status(row.moderation_previous_status, row.status),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    )
    return AdminProductPage(items, page, per_page, total, _pages(total, per_page))


def get_product(product_id: str) -> AdminProductView | None:
    row = db.session.execute(
        db.select(
            Product.id,
            Product.title,
            User.username,
            Product.price,
            Product.status,
            Product.moderation_previous_status,
            Product.created_at,
            Product.updated_at,
        )
        .select_from(Product)
        .join(User, Product.seller_id == User.id)
        .where(Product.id == product_id)
    ).one_or_none()
    if row is None:
        return None
    return AdminProductView(
        id=row.id,
        title=row.title,
        seller_username=row.username,
        price=row.price,
        status=row.status,
        restore_status=_restore_status(row.moderation_previous_status, row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def change_product_status(
    *, actor_id: str, product_id: str, action: str
) -> AdminMutationResult:
    if action not in {"hide", "restore", "delete"}:
        return AdminMutationResult.INVALID_STATE
    product = db.session.get(Product, product_id)
    if product is None:
        return AdminMutationResult.NOT_FOUND
    previous = product.status
    changed = False
    if action == "hide":
        if previous == "hidden":
            pass
        elif previous in {"active", "sold"}:
            product.moderation_previous_status = previous
            product.status = "hidden"
            changed = True
        else:
            return AdminMutationResult.INVALID_STATE
        audit_action = "admin.product.hidden"
    elif action == "restore":
        if previous != "hidden":
            return AdminMutationResult.INVALID_STATE
        product.status = (
            product.moderation_previous_status
            if product.moderation_previous_status in {"active", "sold"}
            else "active"
        )
        product.moderation_previous_status = None
        changed = True
        audit_action = "admin.product.restored"
    else:
        if previous == "deleted":
            pass
        elif previous in {"active", "sold", "hidden"}:
            product.status = "deleted"
            product.moderation_previous_status = None
            changed = True
        else:
            return AdminMutationResult.INVALID_STATE
        audit_action = "admin.product.deleted"

    new_status = product.status
    try:
        add_audit_log(
            actor_user_id=actor_id,
            action=audit_action,
            target_type="product",
            target_id=product.id,
            details={"previous_status": previous, "new_status": new_status},
        )
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        return AdminMutationResult.DATABASE_ERROR
    return AdminMutationResult.OK if changed else AdminMutationResult.IDEMPOTENT


def _target_names(
    rows: tuple,
) -> tuple[dict[str, str], dict[str, str]]:
    user_ids = {row.target_id for row in rows if row.target_type == "user"}
    product_ids = {row.target_id for row in rows if row.target_type == "product"}
    users = (
        {
            user_id: username
            for user_id, username in db.session.execute(
                db.select(User.id, User.username).where(User.id.in_(user_ids))
            )
        }
        if user_ids
        else {}
    )
    products = (
        {
            product_id: title
            for product_id, title in db.session.execute(
                db.select(Product.id, Product.title).where(Product.id.in_(product_ids))
            )
        }
        if product_ids
        else {}
    )
    return users, products


def _target_display(
    target_type: str,
    target_id: str,
    users: dict[str, str],
    products: dict[str, str],
) -> str:
    if target_type == "user":
        return users.get(target_id, "이용할 수 없는 사용자")
    return products.get(target_id, "이용할 수 없는 상품")


def list_reports(
    *,
    query: str | None,
    target_type: str,
    status: str,
    sort: str,
    page: int,
    per_page: int,
) -> AdminReportPage:
    filters = []
    if query:
        filters.append(User.username.contains(query, autoescape=True))
    if target_type in {"user", "product"}:
        filters.append(Report.target_type == target_type)
    if status in {"pending", "confirmed", "rejected"}:
        filters.append(Report.status == status)
    order = (
        (Report.created_at.asc(), Report.id.asc())
        if sort == "oldest"
        else (Report.created_at.desc(), Report.id.desc())
    )
    total = db.session.execute(
        db.select(func.count())
        .select_from(Report)
        .join(User, Report.reporter_id == User.id)
        .where(*filters)
    ).scalar_one()
    rows = tuple(
        db.session.execute(
            db.select(
                Report.id,
                User.username.label("reporter_username"),
                Report.target_type,
                Report.target_id,
                Report.status,
                Report.created_at,
                Report.updated_at,
            )
            .select_from(Report)
            .join(User, Report.reporter_id == User.id)
            .where(*filters)
            .order_by(*order)
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    )
    users, products = _target_names(rows)
    items = tuple(
        AdminReportSummary(
            id=row.id,
            reporter_username=row.reporter_username,
            target_type=row.target_type,
            target_display_name=_target_display(
                row.target_type, row.target_id, users, products
            ),
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    )
    return AdminReportPage(items, page, per_page, total, _pages(total, per_page))


def get_report(report_id: str) -> AdminReportView | None:
    reviewer = aliased(User)
    row = db.session.execute(
        db.select(
            Report.id,
            User.username.label("reporter_username"),
            Report.target_type,
            Report.target_id,
            Report.reason,
            Report.status,
            reviewer.username.label("reviewer_username"),
            Report.reviewed_at,
            Report.created_at,
            Report.updated_at,
        )
        .select_from(Report)
        .join(User, Report.reporter_id == User.id)
        .outerjoin(reviewer, Report.reviewed_by_id == reviewer.id)
        .where(Report.id == report_id)
    ).one_or_none()
    if row is None:
        return None
    users, products = _target_names((row,))
    return AdminReportView(
        id=row.id,
        reporter_username=row.reporter_username,
        target_type=row.target_type,
        target_display_name=_target_display(
            row.target_type, row.target_id, users, products
        ),
        reason=row.reason,
        status=row.status,
        reviewer_username=row.reviewer_username,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def decide_report(
    *, actor_id: str, report_id: str, decision: str
) -> AdminMutationResult:
    status_by_decision = {"confirm": "confirmed", "reject": "rejected"}
    new_status = status_by_decision.get(decision)
    if new_status is None:
        return AdminMutationResult.INVALID_STATE
    report = db.session.get(Report, report_id)
    if report is None:
        return AdminMutationResult.NOT_FOUND
    if report.status != "pending":
        return AdminMutationResult.IDEMPOTENT
    previous = report.status
    report.status = new_status
    report.reviewed_by_id = actor_id
    report.reviewed_at = utc_now()
    report.updated_at = utc_now()
    try:
        add_audit_log(
            actor_user_id=actor_id,
            action=f"admin.report.{new_status}",
            target_type="report",
            target_id=report.id,
            details={
                "target_type": report.target_type,
                "decision": decision,
                "previous_status": previous,
                "new_status": new_status,
            },
        )
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        return AdminMutationResult.DATABASE_ERROR
    return AdminMutationResult.OK


def list_messages(
    *,
    query: str | None,
    scope: str,
    visibility: str,
    sort: str,
    page: int,
    per_page: int,
) -> AdminMessagePage:
    filters = []
    if query:
        filters.append(
            User.username.contains(query, autoescape=True)
            | ChatMessage.body.contains(query, autoescape=True)
        )
    if scope == "global":
        filters.append(ChatMessage.conversation_id.is_(None))
    elif scope == "direct":
        filters.append(ChatMessage.conversation_id.is_not(None))
    if visibility == "visible":
        filters.append(ChatMessage.is_hidden.is_(False))
    elif visibility == "hidden":
        filters.append(ChatMessage.is_hidden.is_(True))
    order = (
        (ChatMessage.created_at.asc(), ChatMessage.id.asc())
        if sort == "oldest"
        else (ChatMessage.created_at.desc(), ChatMessage.id.desc())
    )
    total = db.session.execute(
        db.select(func.count())
        .select_from(ChatMessage)
        .join(User, ChatMessage.sender_id == User.id)
        .where(*filters)
    ).scalar_one()
    items = tuple(
        AdminMessageView(
            id=row.id,
            sender_username=row.username,
            scope=row.scope,
            body=row.body,
            is_hidden=bool(row.is_hidden),
            created_at=row.created_at,
        )
        for row in db.session.execute(
            db.select(
                ChatMessage.id,
                User.username,
                case(
                    (ChatMessage.conversation_id.is_(None), "global"),
                    else_="direct",
                ).label("scope"),
                ChatMessage.body,
                ChatMessage.is_hidden,
                ChatMessage.created_at,
            )
            .select_from(ChatMessage)
            .join(User, ChatMessage.sender_id == User.id)
            .where(*filters)
            .order_by(*order)
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    )
    return AdminMessagePage(items, page, per_page, total, _pages(total, per_page))


def change_message_visibility(
    *, actor_id: str, message_id: str, action: str
) -> AdminMutationResult:
    if action not in {"hide", "show"}:
        return AdminMutationResult.INVALID_STATE
    message = db.session.get(ChatMessage, message_id)
    if message is None:
        return AdminMutationResult.NOT_FOUND
    previous = "hidden" if message.is_hidden else "visible"
    desired_hidden = action == "hide"
    changed = message.is_hidden != desired_hidden
    message.is_hidden = desired_hidden
    new_visibility = "hidden" if desired_hidden else "visible"
    scope = "global" if message.conversation_id is None else "direct"
    audit_action = "admin.message.hidden" if desired_hidden else "admin.message.visible"
    try:
        add_audit_log(
            actor_user_id=actor_id,
            action=audit_action,
            target_type="message",
            target_id=message.id,
            details={
                "previous_visibility": previous,
                "new_visibility": new_visibility,
                "scope": scope,
            },
        )
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        return AdminMutationResult.DATABASE_ERROR
    return AdminMutationResult.OK if changed else AdminMutationResult.IDEMPOTENT


def list_transfers(
    *,
    query: str | None,
    sort: str,
    page: int,
    per_page: int,
) -> AdminTransferPage:
    sender = aliased(User)
    recipient = aliased(User)
    filters = []
    if query:
        filters.append(
            sender.username.contains(query, autoescape=True)
            | recipient.username.contains(query, autoescape=True)
        )
    order = (
        (Transfer.created_at.asc(), Transfer.id.asc())
        if sort == "oldest"
        else (Transfer.created_at.desc(), Transfer.id.desc())
    )
    total = db.session.execute(
        db.select(func.count())
        .select_from(Transfer)
        .join(sender, Transfer.sender_id == sender.id)
        .join(recipient, Transfer.recipient_id == recipient.id)
        .where(*filters)
    ).scalar_one()
    items = tuple(
        AdminTransferView(
            id=row.id,
            sender_username=row.sender_username,
            recipient_username=row.recipient_username,
            amount=row.amount,
            created_at=row.created_at,
        )
        for row in db.session.execute(
            db.select(
                Transfer.id,
                sender.username.label("sender_username"),
                recipient.username.label("recipient_username"),
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
    )
    return AdminTransferPage(items, page, per_page, total, _pages(total, per_page))


def list_audit_logs(
    *,
    query: str | None,
    target_type: str,
    sort: str,
    page: int,
    per_page: int,
) -> AdminAuditLogPage:
    actor = aliased(User)
    filters = []
    if query:
        filters.append(AuditLog.action.contains(query, autoescape=True))
    if target_type in {"user", "product", "report", "message"}:
        filters.append(AuditLog.target_type == target_type)
    order = (
        (AuditLog.created_at.asc(), AuditLog.id.asc())
        if sort == "oldest"
        else (AuditLog.created_at.desc(), AuditLog.id.desc())
    )
    total = db.session.execute(
        db.select(func.count()).select_from(AuditLog).where(*filters)
    ).scalar_one()
    items = tuple(
        AdminAuditLogView(
            actor_username=row.actor_username,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            details=safe_details_for_display(row.action, row.details),
            created_at=row.created_at,
        )
        for row in db.session.execute(
            db.select(
                actor.username.label("actor_username"),
                AuditLog.action,
                AuditLog.target_type,
                AuditLog.target_id,
                AuditLog.details,
                AuditLog.created_at,
            )
            .select_from(AuditLog)
            .outerjoin(actor, AuditLog.actor_user_id == actor.id)
            .where(*filters)
            .order_by(*order)
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    )
    return AdminAuditLogPage(items, page, per_page, total, _pages(total, per_page))

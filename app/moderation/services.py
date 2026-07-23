from enum import Enum, auto
from math import ceil

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.audit.services import add_audit_log
from app.extensions import db
from app.models import Product, Report, User
from app.moderation.policy import (
    EFFECTIVE_REPORT_STATUSES,
    REPORTABLE_PRODUCT_STATUSES,
    ReportReasonError,
    normalize_report_reason,
)
from app.moderation.views import OwnReportPage, OwnReportView, ReportTargetView


class ReportCreateResult(Enum):
    CREATED = auto()
    DUPLICATE = auto()
    SELF_TARGET = auto()
    TARGET_UNAVAILABLE = auto()
    AUTO_RESTRICTED = auto()
    DATABASE_ERROR = auto()


def get_reportable_user(username: str) -> ReportTargetView | None:
    row = db.session.execute(
        db.select(User.username).where(
            User.username == username,
            User.status == "active",
        )
    ).one_or_none()
    if row is None:
        return None
    return ReportTargetView(target_type="user", display_name=row.username)


def get_reportable_product(
    product_id: str, reporter_id: str | None = None
) -> ReportTargetView | None:
    filters = [
        Product.id == product_id,
        Product.status.in_(REPORTABLE_PRODUCT_STATUSES),
    ]
    if reporter_id is not None:
        filters.append(Product.seller_id != reporter_id)
    row = db.session.execute(db.select(Product.title).where(*filters)).one_or_none()
    if row is None:
        return None
    return ReportTargetView(target_type="product", display_name=row.title)


def _already_reported(reporter_id: str, target_type: str, target_id: str) -> bool:
    return (
        db.session.execute(
            db.select(Report.id).where(
                Report.reporter_id == reporter_id,
                Report.target_type == target_type,
                Report.target_id == target_id,
            )
        ).scalar_one_or_none()
        is not None
    )


def _effective_report_count(target_type: str, target_id: str) -> int:
    return db.session.execute(
        db.select(func.count())
        .select_from(Report)
        .where(
            Report.target_type == target_type,
            Report.target_id == target_id,
            Report.status.in_(EFFECTIVE_REPORT_STATUSES),
        )
    ).scalar_one()


def create_user_report(
    *, reporter_id: str, target_username: str, reason: str
) -> ReportCreateResult:
    target = db.session.execute(
        db.select(User).where(
            User.username == target_username,
            User.status == "active",
        )
    ).scalar_one_or_none()
    if target is None:
        return ReportCreateResult.TARGET_UNAVAILABLE
    if target.id == reporter_id:
        return ReportCreateResult.SELF_TARGET
    return _create_report(
        reporter_id=reporter_id,
        target_type="user",
        target_id=target.id,
        reason=reason,
        user_target=target,
    )


def create_product_report(
    *, reporter_id: str, product_id: str, reason: str
) -> ReportCreateResult:
    target = db.session.execute(
        db.select(Product).where(
            Product.id == product_id,
            Product.status.in_(REPORTABLE_PRODUCT_STATUSES),
        )
    ).scalar_one_or_none()
    if target is None:
        return ReportCreateResult.TARGET_UNAVAILABLE
    if target.seller_id == reporter_id:
        return ReportCreateResult.SELF_TARGET
    return _create_report(
        reporter_id=reporter_id,
        target_type="product",
        target_id=target.id,
        reason=reason,
        product_target=target,
    )


def _create_report(
    *,
    reporter_id: str,
    target_type: str,
    target_id: str,
    reason: str,
    user_target: User | None = None,
    product_target: Product | None = None,
) -> ReportCreateResult:
    try:
        reason = normalize_report_reason(reason)
    except ReportReasonError:
        return ReportCreateResult.DATABASE_ERROR
    if _already_reported(reporter_id, target_type, target_id):
        return ReportCreateResult.DUPLICATE

    report = Report(
        reporter_id=reporter_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        status="pending",
    )
    db.session.add(report)
    try:
        db.session.flush()
        add_audit_log(
            actor_user_id=reporter_id,
            action="report.created",
            target_type="report",
            target_id=report.id,
            details={"target_type": target_type},
        )
        count = _effective_report_count(target_type, target_id)
        threshold = current_app.config["REPORT_AUTO_RESTRICTION_THRESHOLD"]
        restricted_user_id = None
        auto_restricted = False
        if (
            product_target is not None
            and count >= threshold
            and product_target.status in REPORTABLE_PRODUCT_STATUSES
        ):
            previous = product_target.status
            product_target.moderation_previous_status = previous
            product_target.status = "hidden"
            add_audit_log(
                actor_user_id=None,
                action="moderation.product.auto_hidden",
                target_type="product",
                target_id=target_id,
                details={
                    "previous_status": previous,
                    "new_status": "hidden",
                    "report_count": count,
                },
            )
            auto_restricted = True
        elif (
            user_target is not None
            and count >= threshold
            and user_target.status == "active"
            and user_target.role == "user"
        ):
            user_target.status = "dormant"
            user_target.auth_version += 1
            add_audit_log(
                actor_user_id=None,
                action="moderation.user.auto_dormant",
                target_type="user",
                target_id=target_id,
                details={
                    "previous_status": "active",
                    "new_status": "dormant",
                    "report_count": count,
                },
            )
            restricted_user_id = target_id
            auto_restricted = True
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if _already_reported(reporter_id, target_type, target_id):
            return ReportCreateResult.DUPLICATE
        return ReportCreateResult.DATABASE_ERROR
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        return ReportCreateResult.DATABASE_ERROR

    if restricted_user_id is not None:
        from app.chat.connections import disconnect_user_sockets

        disconnect_user_sockets(restricted_user_id)
    if auto_restricted:
        return ReportCreateResult.AUTO_RESTRICTED
    return ReportCreateResult.CREATED


def list_own_reports(reporter_id: str, page: int, per_page: int) -> OwnReportPage:
    total = db.session.execute(
        db.select(func.count())
        .select_from(Report)
        .where(Report.reporter_id == reporter_id)
    ).scalar_one()
    rows = tuple(
        db.session.execute(
            db.select(
                Report.target_type,
                Report.target_id,
                Report.reason,
                Report.status,
                Report.created_at,
            )
            .where(Report.reporter_id == reporter_id)
            .order_by(Report.created_at.desc(), Report.id.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    )
    user_ids = {row.target_id for row in rows if row.target_type == "user"}
    product_ids = {row.target_id for row in rows if row.target_type == "product"}
    user_names = (
        {
            user_id: username
            for user_id, username in db.session.execute(
                db.select(User.id, User.username).where(User.id.in_(user_ids))
            )
        }
        if user_ids
        else {}
    )
    product_names = (
        {
            product_id: title
            for product_id, title in db.session.execute(
                db.select(Product.id, Product.title).where(Product.id.in_(product_ids))
            )
        }
        if product_ids
        else {}
    )
    items = tuple(
        OwnReportView(
            target_type=row.target_type,
            target_display_name=(
                user_names.get(row.target_id, "이용할 수 없는 사용자")
                if row.target_type == "user"
                else product_names.get(row.target_id, "이용할 수 없는 상품")
            ),
            reason=row.reason,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    )
    return OwnReportPage(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        pages=ceil(total / per_page),
    )

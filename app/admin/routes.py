from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.admin import bp
from app.admin.decorators import admin_required
from app.admin.forms import (
    AdminAuditFilterForm,
    AdminMessageFilterForm,
    AdminMessageVisibilityForm,
    AdminProductFilterForm,
    AdminProductStatusForm,
    AdminReportDecisionForm,
    AdminReportFilterForm,
    AdminTransferFilterForm,
    AdminUserFilterForm,
    AdminUserStatusForm,
)
from app.admin.services import (
    AdminMutationResult,
    change_message_visibility,
    change_product_status,
    change_user_status,
    dashboard_counts,
    decide_report,
    get_product,
    get_report,
    get_user,
    list_audit_logs,
    list_messages,
    list_products,
    list_reports,
    list_transfers,
    list_users,
    verify_current_password,
)
from app.extensions import limiter
from app.security import authenticated_user_rate_limit_key


admin_read_limit = limiter.shared_limit(
    "120 per minute",
    scope="admin-read",
)
admin_mutation_limit = limiter.shared_limit(
    "60 per hour",
    scope="admin-mutation",
    key_func=authenticated_user_rate_limit_key,
)


def _pagination_values(form):
    if not form.validate():
        abort(400)
    page = form.page.data or 1
    if page > current_app.config["MODERATION_PAGE_MAX"]:
        abort(400)
    return page, current_app.config["ADMIN_ITEMS_PER_PAGE"]


def _pagination_params(form, *field_names):
    return {
        field_name: value
        for field_name in field_names
        if (value := getattr(form, field_name).data) not in (None, "")
    }


def _reauthenticate(form, redirect_endpoint: str, **values):
    if not form.validate_on_submit():
        abort(400)
    if not verify_current_password(current_user, form.current_password.data):
        flash("관리자 재인증 실패", "error")
        return redirect(url_for(redirect_endpoint, **values), code=303)
    return None


def _mutation_response(result: AdminMutationResult, endpoint: str, **values):
    if result is AdminMutationResult.NOT_FOUND:
        abort(404)
    if result in {
        AdminMutationResult.INVALID_STATE,
        AdminMutationResult.SELF_PROTECTED,
        AdminMutationResult.LAST_ADMIN,
    }:
        flash("허용되지 않은 상태 전이입니다.", "error")
    elif result is AdminMutationResult.DATABASE_ERROR:
        flash("요청 처리에 실패했습니다.", "error")
    elif result is AdminMutationResult.IDEMPOTENT:
        flash("이미 요청한 상태입니다.", "success")
    else:
        flash("관리자 조치가 적용되었습니다.", "success")
    return redirect(url_for(endpoint, **values), code=303)


@bp.get("")
@admin_required
@admin_read_limit
def dashboard():
    return render_template("admin/dashboard.html", counts=dashboard_counts())


@bp.get("/users")
@admin_required
@admin_read_limit
def users():
    form = AdminUserFilterForm(request.args)
    page, per_page = _pagination_values(form)
    pagination_params = _pagination_params(form, "q", "role", "status", "sort")
    result_page = list_users(
        query=form.q.data or None,
        role=form.role.data,
        status=form.status.data,
        sort=form.sort.data,
        page=page,
        per_page=per_page,
    )
    return render_template(
        "admin/users.html",
        form=form,
        page=result_page,
        pagination_endpoint="admin.users",
        pagination_params=pagination_params,
    )


@bp.get("/users/<string:username>")
@admin_required
@admin_read_limit
def user_detail(username: str):
    user = get_user(username)
    if user is None:
        abort(404)
    return render_template(
        "admin/user_detail.html",
        managed_user=user,
        status_form=AdminUserStatusForm(),
    )


@bp.post("/users/<string:username>/status")
@admin_required
@admin_mutation_limit
def user_status(username: str):
    if get_user(username) is None:
        abort(404)
    form = AdminUserStatusForm()
    failure = _reauthenticate(form, "admin.user_detail", username=username)
    if failure is not None:
        return failure
    result = change_user_status(
        actor_id=current_user.id,
        target_username=username,
        new_status=form.status.data,
    )
    return _mutation_response(result, "admin.user_detail", username=username)


@bp.get("/products")
@admin_required
@admin_read_limit
def products():
    form = AdminProductFilterForm(request.args)
    page, per_page = _pagination_values(form)
    pagination_params = _pagination_params(form, "q", "status", "sort")
    result_page = list_products(
        query=form.q.data or None,
        status=form.status.data,
        sort=form.sort.data,
        page=page,
        per_page=per_page,
    )
    return render_template(
        "admin/products.html",
        form=form,
        page=result_page,
        pagination_endpoint="admin.products",
        pagination_params=pagination_params,
    )


@bp.get("/products/<uuid:product_id>")
@admin_required
@admin_read_limit
def product_detail(product_id):
    product = get_product(str(product_id))
    if product is None:
        abort(404)
    return render_template(
        "admin/product_detail.html",
        product=product,
        status_form=AdminProductStatusForm(),
    )


@bp.post("/products/<uuid:product_id>/status")
@admin_required
@admin_mutation_limit
def product_status(product_id):
    canonical_id = str(product_id)
    if get_product(canonical_id) is None:
        abort(404)
    form = AdminProductStatusForm()
    failure = _reauthenticate(form, "admin.product_detail", product_id=canonical_id)
    if failure is not None:
        return failure
    result = change_product_status(
        actor_id=current_user.id,
        product_id=canonical_id,
        action=form.action.data,
    )
    return _mutation_response(result, "admin.product_detail", product_id=canonical_id)


@bp.get("/reports")
@admin_required
@admin_read_limit
def reports():
    form = AdminReportFilterForm(request.args)
    page, per_page = _pagination_values(form)
    pagination_params = _pagination_params(form, "q", "target_type", "status", "sort")
    result_page = list_reports(
        query=form.q.data or None,
        target_type=form.target_type.data,
        status=form.status.data,
        sort=form.sort.data,
        page=page,
        per_page=per_page,
    )
    return render_template(
        "admin/reports.html",
        form=form,
        page=result_page,
        pagination_endpoint="admin.reports",
        pagination_params=pagination_params,
    )


@bp.get("/reports/<uuid:report_id>")
@admin_required
@admin_read_limit
def report_detail(report_id):
    report = get_report(str(report_id))
    if report is None:
        abort(404)
    return render_template(
        "admin/report_detail.html",
        report=report,
        decision_form=AdminReportDecisionForm(),
    )


@bp.post("/reports/<uuid:report_id>/decision")
@admin_required
@admin_mutation_limit
def report_decision(report_id):
    canonical_id = str(report_id)
    if get_report(canonical_id) is None:
        abort(404)
    form = AdminReportDecisionForm()
    failure = _reauthenticate(form, "admin.report_detail", report_id=canonical_id)
    if failure is not None:
        return failure
    result = decide_report(
        actor_id=current_user.id,
        report_id=canonical_id,
        decision=form.decision.data,
    )
    return _mutation_response(result, "admin.report_detail", report_id=canonical_id)


@bp.get("/messages")
@admin_required
@admin_read_limit
def messages():
    form = AdminMessageFilterForm(request.args)
    page, per_page = _pagination_values(form)
    pagination_params = _pagination_params(form, "q", "scope", "visibility", "sort")
    result_page = list_messages(
        query=form.q.data or None,
        scope=form.scope.data,
        visibility=form.visibility.data,
        sort=form.sort.data,
        page=page,
        per_page=per_page,
    )
    return render_template(
        "admin/messages.html",
        form=form,
        page=result_page,
        visibility_form=AdminMessageVisibilityForm(),
        pagination_endpoint="admin.messages",
        pagination_params=pagination_params,
    )


@bp.post("/messages/<uuid:message_id>/visibility")
@admin_required
@admin_mutation_limit
def message_visibility(message_id):
    form = AdminMessageVisibilityForm()
    failure = _reauthenticate(form, "admin.messages")
    if failure is not None:
        return failure
    result = change_message_visibility(
        actor_id=current_user.id,
        message_id=str(message_id),
        action=form.action.data,
    )
    return _mutation_response(result, "admin.messages")


@bp.get("/transfers")
@admin_required
@admin_read_limit
def transfers():
    form = AdminTransferFilterForm(request.args)
    page, per_page = _pagination_values(form)
    pagination_params = _pagination_params(form, "q", "sort")
    result_page = list_transfers(
        query=form.q.data or None,
        sort=form.sort.data,
        page=page,
        per_page=per_page,
    )
    return render_template(
        "admin/transfers.html",
        form=form,
        page=result_page,
        pagination_endpoint="admin.transfers",
        pagination_params=pagination_params,
    )


@bp.get("/audit-logs")
@admin_required
@admin_read_limit
def audit_logs():
    form = AdminAuditFilterForm(request.args)
    page, per_page = _pagination_values(form)
    pagination_params = _pagination_params(form, "q", "target_type", "sort")
    result_page = list_audit_logs(
        query=form.q.data or None,
        target_type=form.target_type.data,
        sort=form.sort.data,
        page=page,
        per_page=per_page,
    )
    return render_template(
        "admin/audit_logs.html",
        form=form,
        page=result_page,
        pagination_endpoint="admin.audit_logs",
        pagination_params=pagination_params,
    )

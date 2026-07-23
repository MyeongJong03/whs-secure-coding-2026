from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_limiter.util import get_remote_address
from wtforms import IntegerField
from wtforms.form import Form
from wtforms.validators import NumberRange, Optional

from app.extensions import limiter
from app.moderation import bp
from app.moderation.forms import ReportProductForm, ReportUserForm
from app.moderation.services import (
    ReportCreateResult,
    create_product_report,
    create_user_report,
    get_reportable_product,
    get_reportable_user,
    list_own_reports,
)
from app.security import authenticated_user_rate_limit_key, no_store


class ReportPageForm(Form):
    page = IntegerField(
        validators=[Optional(), NumberRange(min=1, max=1000)], default=1
    )


report_submission_limit = limiter.shared_limit(
    "10 per hour",
    scope="moderation-report-submission",
    key_func=authenticated_user_rate_limit_key,
    methods=["POST"],
)


def _handle_result(result: ReportCreateResult):
    if result is ReportCreateResult.DUPLICATE:
        flash("이미 신고한 대상입니다.", "error")
    elif result in {
        ReportCreateResult.SELF_TARGET,
        ReportCreateResult.TARGET_UNAVAILABLE,
    }:
        flash("신고할 수 없는 대상입니다.", "error")
    elif result is ReportCreateResult.DATABASE_ERROR:
        flash("요청 처리에 실패했습니다.", "error")
    else:
        flash("신고가 접수되었습니다.", "success")
    return redirect(url_for("moderation.mine"), code=303)


@bp.route("/reports/users/<string:username>/new", methods=["GET", "POST"])
@login_required
@report_submission_limit
@no_store
def report_user(username: str):
    target = get_reportable_user(username)
    if target is None:
        abort(404)
    if current_user.username == username:
        if request.method == "POST":
            return _handle_result(ReportCreateResult.SELF_TARGET)
        abort(404)
    form = ReportUserForm()
    if form.validate_on_submit():
        return _handle_result(
            create_user_report(
                reporter_id=current_user.id,
                target_username=username,
                reason=form.reason.data,
            )
        )
    status = 400 if form.is_submitted() else 200
    return render_template(
        "moderation/report_user.html", form=form, target=target
    ), status


@bp.route("/reports/products/<uuid:product_id>/new", methods=["GET", "POST"])
@login_required
@report_submission_limit
@no_store
def report_product(product_id):
    canonical_id = str(product_id)
    target = get_reportable_product(canonical_id, current_user.id)
    if target is None:
        abort(404)
    form = ReportProductForm()
    if form.validate_on_submit():
        return _handle_result(
            create_product_report(
                reporter_id=current_user.id,
                product_id=canonical_id,
                reason=form.reason.data,
            )
        )
    status = 400 if form.is_submitted() else 200
    return render_template(
        "moderation/report_product.html", form=form, target=target
    ), status


@bp.get("/me/reports")
@login_required
@limiter.limit("60 per minute", key_func=get_remote_address)
@no_store
def mine():
    form = ReportPageForm(request.args)
    if not form.validate():
        abort(400)
    page_number = form.page.data or 1
    if page_number > current_app.config["MODERATION_PAGE_MAX"]:
        abort(400)
    page = list_own_reports(
        current_user.id,
        page_number,
        current_app.config["REPORTS_PER_PAGE"],
    )
    return render_template("moderation/mine.html", page=page)

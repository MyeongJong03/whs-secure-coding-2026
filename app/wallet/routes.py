import secrets

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import limiter
from app.security import authenticated_user_rate_limit_key, no_store
from app.wallet import bp
from app.wallet.forms import TransferForm, TransferHistoryForm
from app.wallet.policy import valid_idempotency_token
from app.wallet.services import (
    TransferResult,
    create_transfer,
    get_transfer_detail,
    get_wallet_summary,
    list_transfer_history,
)


wallet_read_limit = limiter.shared_limit("60 per minute", scope="wallet-read")
transfer_minute_limit = limiter.limit(
    "3 per minute",
    key_func=authenticated_user_rate_limit_key,
)
transfer_hour_limit = limiter.limit(
    "10 per hour",
    key_func=authenticated_user_rate_limit_key,
)


def _new_idempotency_token() -> str:
    return secrets.token_urlsafe(current_app.config["TRANSFER_IDEMPOTENCY_TOKEN_BYTES"])


def _render_transfer_error(
    form: TransferForm,
    message: str,
    status_code: int,
    *,
    rotate_idempotency_token: bool = True,
):
    form.current_password.data = None
    if rotate_idempotency_token or not valid_idempotency_token(
        form.idempotency_token.data
    ):
        form.idempotency_token.data = _new_idempotency_token()
    flash(message, "error")
    return render_template("wallet/transfer.html", form=form), status_code


@bp.get("")
@login_required
@wallet_read_limit
@no_store
def index():
    form = TransferHistoryForm(request.args)
    if not form.validate():
        abort(400)
    page_number = form.page.data or 1
    summary = get_wallet_summary(current_user.id)
    if summary is None:
        abort(404)
    page = list_transfer_history(
        user_id=current_user.id,
        direction=form.direction.data,
        sort=form.sort.data,
        page=page_number,
        per_page=current_app.config["TRANSFER_HISTORY_PER_PAGE"],
    )
    pagination_params = {
        "direction": form.direction.data,
        "sort": form.sort.data,
    }
    return render_template(
        "wallet/index.html",
        form=form,
        wallet=summary,
        page=page,
        pagination_params=pagination_params,
    )


@bp.get("/transfer")
@login_required
@wallet_read_limit
@no_store
def transfer_form():
    form = TransferForm()
    form.idempotency_token.data = _new_idempotency_token()
    return render_template("wallet/transfer.html", form=form)


@bp.post("/transfer")
@login_required
@transfer_minute_limit
@transfer_hour_limit
@no_store
def transfer_submit():
    form = TransferForm()
    if not form.validate_on_submit():
        return _render_transfer_error(form, "입력값을 확인해 주세요.", 400)

    outcome = create_transfer(
        sender_id=current_user.id,
        recipient_username=form.recipient_username.data,
        amount=form.amount.data,
        current_password=form.current_password.data,
        raw_idempotency_token=form.idempotency_token.data,
    )
    if outcome.result in {TransferResult.CREATED, TransferResult.IDEMPOTENT}:
        if outcome.result is TransferResult.CREATED:
            flash("가상 포인트 송금이 완료되었습니다.", "success")
        else:
            flash("이미 처리된 송금 결과를 표시합니다.", "success")
        return redirect(
            url_for("wallet.transfer_detail", transfer_id=outcome.transfer_id),
            code=303,
        )
    if outcome.result is TransferResult.IDEMPOTENCY_CONFLICT:
        return _render_transfer_error(
            form,
            "중복 요청 정보가 일치하지 않습니다. 송금을 다시 시작해 주세요.",
            409,
        )
    if outcome.result is TransferResult.SELF_TRANSFER:
        return _render_transfer_error(form, "자기 자신에게 송금할 수 없습니다.", 400)
    if outcome.result is TransferResult.RECIPIENT_UNAVAILABLE:
        return _render_transfer_error(form, "수신자를 확인할 수 없습니다.", 400)
    if outcome.result is TransferResult.CURRENT_PASSWORD_INVALID:
        return _render_transfer_error(form, "현재 비밀번호가 올바르지 않습니다.", 400)
    if outcome.result is TransferResult.INSUFFICIENT_FUNDS:
        return _render_transfer_error(form, "잔액이 부족합니다.", 400)
    return _render_transfer_error(
        form,
        "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        500,
        rotate_idempotency_token=False,
    )


@bp.get("/transfers/<uuid:transfer_id>")
@login_required
@wallet_read_limit
@no_store
def transfer_detail(transfer_id):
    transfer = get_transfer_detail(
        user_id=current_user.id,
        transfer_id=str(transfer_id),
    )
    if transfer is None:
        abort(404)
    return render_template("wallet/detail.html", transfer=transfer)

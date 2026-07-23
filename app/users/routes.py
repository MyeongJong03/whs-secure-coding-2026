from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import limiter
from app.chat.connections import disconnect_user_sockets
from app.security import (
    authenticated_user_rate_limit_key,
    establish_authenticated_session,
    no_store,
)
from app.users import bp
from app.users.forms import BioForm, PasswordChangeForm, UserSearchForm
from app.users.services import (
    PasswordChangeResult,
    change_password,
    get_public_user,
    search_public_users,
    update_bio,
)


USERS_PER_PAGE = 20


def render_me(*, bio_form=None, password_form=None, status=200):
    return (
        render_template(
            "users/me.html",
            bio_form=bio_form or BioForm(),
            password_form=password_form or PasswordChangeForm(),
            wallet=current_user.wallet,
        ),
        status,
    )


@bp.get("/users")
@limiter.limit("60 per minute")
def index():
    form = UserSearchForm(request.args)
    if not form.validate():
        return render_template("users/index.html", form=form, pagination=None), 400

    pagination = search_public_users(
        form.q.data,
        page=form.page.data or 1,
        per_page=USERS_PER_PAGE,
    )
    return render_template("users/index.html", form=form, pagination=pagination)


@bp.get("/users/<string:username>")
def profile(username: str):
    public_user = get_public_user(username)
    if public_user is None:
        abort(404)
    return render_template("users/profile.html", profile_user=public_user)


@bp.get("/me")
@login_required
@no_store
def me():
    return render_me()


@bp.post("/me/bio")
@login_required
@limiter.limit("30 per hour", key_func=authenticated_user_rate_limit_key)
@no_store
def change_bio():
    form = BioForm()
    if not form.validate_on_submit():
        return render_me(bio_form=form, status=400)
    if not update_bio(current_user, form.bio.data or ""):
        flash("소개글을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error")
        return render_me(bio_form=form, status=400)
    flash("소개글을 변경했습니다.", "success")
    return redirect(url_for("users.me"), code=303)


@bp.post("/me/password")
@login_required
@limiter.limit("5 per hour", key_func=authenticated_user_rate_limit_key)
@no_store
def change_own_password():
    form = PasswordChangeForm()
    if not form.validate_on_submit():
        return render_me(password_form=form, status=400)

    result = change_password(
        current_user, form.current_password.data, form.new_password.data
    )
    if result is PasswordChangeResult.CURRENT_PASSWORD_INVALID:
        form.current_password.errors.append("현재 비밀번호가 올바르지 않습니다.")
        return render_me(password_form=form, status=400)
    if result is PasswordChangeResult.PASSWORD_UNCHANGED:
        form.new_password.errors.append("현재 비밀번호와 다른 비밀번호를 입력하세요.")
        return render_me(password_form=form, status=400)
    if result is PasswordChangeResult.DATABASE_ERROR:
        flash("비밀번호를 변경하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error")
        return render_me(password_form=form, status=400)

    user_id = current_user.get_id()
    if user_id is not None:
        disconnect_user_sockets(user_id)
    establish_authenticated_session(current_user)
    flash("비밀번호를 변경했습니다.", "success")
    return redirect(url_for("users.me"), code=303)

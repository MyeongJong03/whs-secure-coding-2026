from flask import flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, logout_user

from app.auth import bp
from app.auth.forms import LoginForm, LogoutForm, RegistrationForm
from app.auth.services import RegistrationResult, authenticate_user, register_user
from app.chat.connections import disconnect_user_sockets
from app.extensions import limiter
from app.security import establish_authenticated_session, no_store


GENERIC_LOGIN_ERROR = "사용자명 또는 비밀번호가 올바르지 않습니다."


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
@no_store
def register():
    if current_user.is_authenticated:
        return redirect(url_for("users.me"), code=303)

    form = RegistrationForm()
    if form.validate_on_submit():
        result = register_user(form.username.data, form.password.data)
        if result is RegistrationResult.CREATED:
            flash("회원가입이 완료되었습니다. 로그인해 주세요.", "success")
            return redirect(url_for("auth.login"), code=303)
        if result is RegistrationResult.DUPLICATE_USERNAME:
            form.username.errors.append("이미 사용 중인 사용자명입니다.")
        else:
            flash("요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error")
        return render_template("auth/register.html", form=form), 400
    if form.is_submitted():
        return render_template("auth/register.html", form=form), 400
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
@limiter.limit("20 per hour", methods=["POST"])
@no_store
def login():
    if current_user.is_authenticated:
        return redirect(url_for("users.me"), code=303)

    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate_user(form.username.data, form.password.data)
        if user is not None:
            establish_authenticated_session(user)
            return redirect(url_for("users.me"), code=303)
        flash(GENERIC_LOGIN_ERROR, "error")
        return render_template("auth/login.html", form=form), 401
    if form.is_submitted():
        flash(GENERIC_LOGIN_ERROR, "error")
        return render_template("auth/login.html", form=form), 401
    return render_template("auth/login.html", form=form)


@bp.post("/logout")
@login_required
@no_store
def logout():
    form = LogoutForm()
    if not form.validate_on_submit():
        return render_template("errors/error.html", code=400), 400
    user_id = current_user.get_id()
    if user_id is not None:
        disconnect_user_sockets(user_id)
    logout_user()
    session.clear()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("auth.login"), code=303)

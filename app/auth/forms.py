import re

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import EqualTo, InputRequired, Length, ValidationError


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def strip_username(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_username_policy(_form, field) -> None:
    if not USERNAME_PATTERN.fullmatch(field.data or ""):
        raise ValidationError("사용자명은 영문, 숫자, 밑줄만 사용할 수 있습니다.")


class RegistrationForm(FlaskForm):
    username = StringField(
        "사용자명",
        filters=[strip_username],
        validators=[InputRequired(), Length(min=4, max=32), validate_username_policy],
    )
    password = PasswordField(
        "비밀번호", validators=[InputRequired(), Length(min=12, max=128)]
    )
    password_confirm = PasswordField(
        "비밀번호 확인",
        validators=[
            InputRequired(),
            Length(min=12, max=128),
            EqualTo("password", message="비밀번호가 일치하지 않습니다."),
        ],
    )
    submit = SubmitField("회원가입")


class LoginForm(FlaskForm):
    username = StringField(
        "사용자명",
        filters=[strip_username],
        validators=[InputRequired(), Length(min=4, max=32), validate_username_policy],
    )
    password = PasswordField("비밀번호", validators=[InputRequired(), Length(max=128)])
    submit = SubmitField("로그인")


class LogoutForm(FlaskForm):
    submit = SubmitField("로그아웃")

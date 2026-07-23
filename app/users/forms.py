from flask_wtf import FlaskForm
from wtforms import IntegerField, PasswordField, StringField, SubmitField, TextAreaField
from wtforms.form import Form
from wtforms.validators import EqualTo, InputRequired, Length, NumberRange, Optional


def strip_search_query(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


class UserSearchForm(Form):
    q = StringField(
        "사용자명 검색",
        filters=[strip_search_query],
        validators=[Optional(), Length(max=32)],
    )
    page = IntegerField(
        "페이지", default=1, validators=[Optional(), NumberRange(min=1, max=1000)]
    )


class BioForm(FlaskForm):
    bio = TextAreaField("소개글", validators=[Optional(), Length(max=500)])
    submit = SubmitField("소개글 저장")


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField(
        "현재 비밀번호", validators=[InputRequired(), Length(max=128)]
    )
    new_password = PasswordField(
        "새 비밀번호", validators=[InputRequired(), Length(min=12, max=128)]
    )
    new_password_confirm = PasswordField(
        "새 비밀번호 확인",
        validators=[
            InputRequired(),
            Length(min=12, max=128),
            EqualTo("new_password", message="새 비밀번호가 일치하지 않습니다."),
        ],
    )
    submit = SubmitField("비밀번호 변경")

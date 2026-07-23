from flask import current_app
from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField
from wtforms.form import Form
from wtforms.validators import (
    InputRequired,
    Length,
    Optional,
    Regexp,
    ValidationError,
)


class ChatPageForm(Form):
    page = IntegerField(
        "페이지",
        default=1,
        validators=[Optional()],
    )

    def validate_page(self, field) -> None:
        if field.data is not None and not (
            1 <= field.data <= current_app.config["CHAT_PAGE_MAX"]
        ):
            raise ValidationError("올바른 페이지를 입력하세요.")


class DirectStartForm(FlaskForm):
    username = StringField(
        "상대 사용자명",
        filters=[lambda value: value.strip() if isinstance(value, str) else ""],
        validators=[
            InputRequired(),
            Length(min=4, max=32),
            Regexp(r"^[A-Za-z0-9_]+$"),
        ],
    )
    submit = SubmitField("대화 시작")

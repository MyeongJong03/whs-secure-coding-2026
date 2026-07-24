from flask import current_app
from flask_wtf import FlaskForm
from wtforms import (
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.form import Form
from wtforms.validators import (
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from app.wallet.policy import normalize_recipient_username, valid_idempotency_token


def strip_recipient_username(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_recipient_username(_form, field) -> None:
    if normalize_recipient_username(field.data) is None:
        raise ValidationError("사용자명은 영문, 숫자, 밑줄만 사용할 수 있습니다.")


def validate_token_format(_form, field) -> None:
    if not valid_idempotency_token(field.data):
        raise ValidationError("송금 요청을 다시 시작해 주세요.")


class TransferForm(FlaskForm):
    recipient_username = StringField(
        "수신자 사용자명",
        filters=[strip_recipient_username],
        validators=[
            InputRequired(),
            Length(min=4, max=32),
            validate_recipient_username,
        ],
    )
    amount = IntegerField(
        "송금액",
        validators=[
            InputRequired(),
            NumberRange(min=1, max=1_000_000_000),
        ],
    )
    current_password = PasswordField(
        "현재 비밀번호",
        validators=[InputRequired(), Length(max=128)],
    )
    idempotency_token = HiddenField(
        validators=[
            InputRequired(),
            Length(min=43, max=43),
            validate_token_format,
        ]
    )
    submit = SubmitField("가상 포인트 송금")


class TransferHistoryForm(Form):
    page = IntegerField(
        "페이지",
        validators=[Optional(), NumberRange(min=1, max=1000)],
        default=1,
    )
    direction = SelectField(
        "방향",
        choices=(
            ("all", "전체"),
            ("sent", "보낸 내역"),
            ("received", "받은 내역"),
        ),
        default="all",
    )
    sort = SelectField(
        "정렬",
        choices=(("newest", "최신순"), ("oldest", "오래된순")),
        default="newest",
    )

    def validate_page(self, field) -> None:
        if (
            field.data is not None
            and field.data > current_app.config["TRANSFER_PAGE_MAX"]
        ):
            raise ValidationError("페이지 범위를 벗어났습니다.")

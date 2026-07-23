from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import InputRequired, ValidationError

from app.moderation.policy import ReportReasonError, normalize_report_reason


def validate_and_normalize_reason(_form, field) -> None:
    try:
        field.data = normalize_report_reason(field.data)
    except ReportReasonError as error:
        raise ValidationError(str(error)) from error


class ReportUserForm(FlaskForm):
    reason = TextAreaField(
        "신고 사유",
        validators=[InputRequired(), validate_and_normalize_reason],
    )


class ReportProductForm(FlaskForm):
    reason = TextAreaField(
        "신고 사유",
        validators=[InputRequired(), validate_and_normalize_reason],
    )

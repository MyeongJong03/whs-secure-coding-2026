from flask_wtf import FlaskForm
from wtforms import IntegerField, PasswordField, SelectField, StringField
from wtforms.form import Form
from wtforms.validators import InputRequired, Length, NumberRange, Optional


def strip_text(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


class AdminReauthenticationForm(FlaskForm):
    current_password = PasswordField(
        "현재 관리자 비밀번호",
        validators=[InputRequired(), Length(max=128)],
    )


class AdminUserStatusForm(AdminReauthenticationForm):
    status = SelectField(
        "새 상태",
        choices=(("active", "활성"), ("dormant", "휴면")),
        validators=[InputRequired()],
    )


class AdminProductStatusForm(AdminReauthenticationForm):
    action = SelectField(
        "조치",
        choices=(("hide", "숨김"), ("restore", "복구"), ("delete", "삭제")),
        validators=[InputRequired()],
    )


class AdminReportDecisionForm(AdminReauthenticationForm):
    decision = SelectField(
        "결정",
        choices=(("confirm", "확인"), ("reject", "기각")),
        validators=[InputRequired()],
    )


class AdminMessageVisibilityForm(AdminReauthenticationForm):
    action = SelectField(
        "표시 상태",
        choices=(("hide", "숨김"), ("show", "표시")),
        validators=[InputRequired()],
    )


class AdminPageForm(Form):
    page = IntegerField(
        "페이지",
        validators=[Optional(), NumberRange(min=1, max=1000)],
        default=1,
    )
    sort = SelectField(
        "정렬",
        choices=(("newest", "최신순"), ("oldest", "오래된순")),
        default="newest",
    )


class AdminUserFilterForm(AdminPageForm):
    q = StringField(
        "사용자명",
        filters=[strip_text],
        validators=[Optional(), Length(max=100)],
    )
    role = SelectField(
        "역할",
        choices=(("all", "전체"), ("user", "일반 사용자"), ("admin", "관리자")),
        default="all",
    )
    status = SelectField(
        "상태",
        choices=(("all", "전체"), ("active", "활성"), ("dormant", "휴면")),
        default="all",
    )


class AdminProductFilterForm(AdminPageForm):
    q = StringField(
        "상품명 또는 판매자",
        filters=[strip_text],
        validators=[Optional(), Length(max=100)],
    )
    status = SelectField(
        "상태",
        choices=(
            ("all", "전체"),
            ("active", "판매 중"),
            ("sold", "판매 완료"),
            ("hidden", "숨김"),
            ("deleted", "삭제"),
        ),
        default="all",
    )


class AdminReportFilterForm(AdminPageForm):
    q = StringField(
        "신고자",
        filters=[strip_text],
        validators=[Optional(), Length(max=100)],
    )
    target_type = SelectField(
        "대상 유형",
        choices=(("all", "전체"), ("user", "사용자"), ("product", "상품")),
        default="all",
    )
    status = SelectField(
        "처리 상태",
        choices=(
            ("all", "전체"),
            ("pending", "대기"),
            ("confirmed", "확인"),
            ("rejected", "기각"),
        ),
        default="all",
    )


class AdminMessageFilterForm(AdminPageForm):
    q = StringField(
        "발신자 또는 본문",
        filters=[strip_text],
        validators=[Optional(), Length(max=100)],
    )
    scope = SelectField(
        "범위",
        choices=(("all", "전체"), ("global", "전체"), ("direct", "1대1")),
        default="all",
    )
    visibility = SelectField(
        "표시 상태",
        choices=(("all", "전체"), ("visible", "표시"), ("hidden", "숨김")),
        default="all",
    )


class AdminTransferFilterForm(AdminPageForm):
    q = StringField(
        "송신자 또는 수신자",
        filters=[strip_text],
        validators=[Optional(), Length(max=100)],
    )


class AdminAuditFilterForm(AdminPageForm):
    q = StringField(
        "action",
        filters=[strip_text],
        validators=[Optional(), Length(max=100)],
    )
    target_type = SelectField(
        "대상 유형",
        choices=(
            ("all", "전체"),
            ("user", "사용자"),
            ("product", "상품"),
            ("report", "신고"),
            ("message", "메시지"),
            ("transfer", "송금"),
        ),
        default="all",
    )

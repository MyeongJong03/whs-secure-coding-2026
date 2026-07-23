from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import (
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.form import Form
from wtforms.validators import (
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from app.products.policy import (
    DESCRIPTION_MAX_LENGTH,
    DESCRIPTION_MIN_LENGTH,
    PRICE_MAX,
    PRICE_MIN,
    SEARCH_PAGE_MAX,
    SEARCH_PAGE_MIN,
    SEARCH_QUERY_MAX_LENGTH,
    SEARCH_SORTS,
    SEARCH_STATUSES,
    TITLE_MAX_LENGTH,
    TITLE_MIN_LENGTH,
)


def strip_text(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


class ProductFieldsMixin:
    title = StringField(
        "상품명",
        filters=[strip_text],
        validators=[
            InputRequired(),
            Length(min=TITLE_MIN_LENGTH, max=TITLE_MAX_LENGTH),
        ],
    )
    description = TextAreaField(
        "설명",
        filters=[strip_text],
        validators=[
            InputRequired(),
            Length(min=DESCRIPTION_MIN_LENGTH, max=DESCRIPTION_MAX_LENGTH),
        ],
    )
    price = IntegerField(
        "가격",
        validators=[
            InputRequired(),
            NumberRange(min=PRICE_MIN, max=PRICE_MAX),
        ],
    )


class CreateProductForm(ProductFieldsMixin, FlaskForm):
    image = FileField("상품 이미지", validators=[FileRequired()])
    submit = SubmitField("상품 등록")


class EditProductForm(ProductFieldsMixin, FlaskForm):
    image = FileField("교체 이미지", validators=[Optional()])
    submit = SubmitField("상품 수정")


class ProductStatusForm(FlaskForm):
    status = SelectField(
        "판매 상태",
        choices=(("active", "판매 중"), ("sold", "판매 완료")),
        validators=[InputRequired()],
    )
    submit = SubmitField("상태 변경")


class DeleteProductForm(FlaskForm):
    submit = SubmitField("상품 삭제")


class ProductSearchForm(Form):
    q = StringField(
        "상품 검색",
        filters=[strip_text],
        validators=[Optional(), Length(max=SEARCH_QUERY_MAX_LENGTH)],
    )
    status = SelectField(
        "상태",
        choices=(("all", "전체"), ("active", "판매 중"), ("sold", "판매 완료")),
        default="all",
    )
    min_price = IntegerField(
        "최소 가격",
        validators=[Optional(), NumberRange(min=PRICE_MIN, max=PRICE_MAX)],
    )
    max_price = IntegerField(
        "최대 가격",
        validators=[Optional(), NumberRange(min=PRICE_MIN, max=PRICE_MAX)],
    )
    sort = SelectField(
        "정렬",
        choices=(
            ("newest", "최신순"),
            ("oldest", "오래된순"),
            ("price_low", "낮은 가격순"),
            ("price_high", "높은 가격순"),
            ("title", "상품명순"),
        ),
        default="newest",
    )
    page = IntegerField(
        "페이지",
        default=1,
        validators=[
            Optional(),
            NumberRange(min=SEARCH_PAGE_MIN, max=SEARCH_PAGE_MAX),
        ],
    )

    def validate_status(self, field) -> None:
        if field.data not in SEARCH_STATUSES:
            raise ValidationError("올바른 상태를 선택하세요.")

    def validate_sort(self, field) -> None:
        if field.data not in SEARCH_SORTS:
            raise ValidationError("올바른 정렬 기준을 선택하세요.")

    def validate_max_price(self, field) -> None:
        if (
            self.min_price.data is not None
            and field.data is not None
            and self.min_price.data > field.data
        ):
            raise ValidationError("최대 가격은 최소 가격 이상이어야 합니다.")

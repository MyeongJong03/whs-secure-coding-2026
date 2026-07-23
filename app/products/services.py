from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from math import ceil

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import Product, User
from app.products.images import (
    ImageValidationError,
    remove_product_image,
    store_product_image,
)
from app.products.policy import (
    CREATED_STATUS,
    OWNER_EDITABLE_STATUSES,
    PRODUCTS_PER_PAGE,
    PUBLIC_STATUSES,
)


@dataclass(frozen=True, slots=True)
class PublicProductSummary:
    id: str
    title: str
    price: int
    status: str
    seller_username: str


@dataclass(frozen=True, slots=True)
class PublicProductDetail:
    id: str
    title: str
    description: str
    price: int
    status: str
    seller_username: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PublicProductPage:
    items: tuple[PublicProductSummary, ...]
    page: int
    per_page: int
    total: int
    pages: int
    has_prev: bool
    has_next: bool
    prev_num: int | None
    next_num: int | None


@dataclass(frozen=True, slots=True)
class OwnerProductView:
    id: str
    title: str
    description: str
    price: int
    status: str
    created_at: datetime
    updated_at: datetime
    has_image: bool


@dataclass(frozen=True, slots=True)
class ImageAccess:
    filename: str | None
    is_public: bool


class MutationResult(Enum):
    OK = auto()
    NOT_FOUND = auto()
    INVALID_STATE = auto()
    DATABASE_ERROR = auto()


SORT_EXPRESSIONS = {
    "newest": (Product.created_at.desc(), Product.id.desc()),
    "oldest": (Product.created_at.asc(), Product.id.asc()),
    "price_low": (Product.price.asc(), Product.id.asc()),
    "price_high": (Product.price.desc(), Product.id.desc()),
    "title": (Product.title.asc(), Product.id.asc()),
}


def search_public_products(
    *,
    query: str | None,
    status: str,
    min_price: int | None,
    max_price: int | None,
    sort: str,
    page: int,
) -> PublicProductPage:
    filters = [
        Product.status.in_(PUBLIC_STATUSES),
        User.status == "active",
    ]
    if status in PUBLIC_STATUSES:
        filters.append(Product.status == status)
    if query:
        filters.append(
            Product.title.contains(query, autoescape=True)
            | Product.description.contains(query, autoescape=True)
        )
    if min_price is not None:
        filters.append(Product.price >= min_price)
    if max_price is not None:
        filters.append(Product.price <= max_price)

    join_condition = Product.seller_id == User.id
    total = db.session.execute(
        db.select(func.count())
        .select_from(Product)
        .join(User, join_condition)
        .where(*filters)
    ).scalar_one()
    statement = (
        db.select(
            Product.id,
            Product.title,
            Product.price,
            Product.status,
            User.username,
        )
        .select_from(Product)
        .join(User, join_condition)
        .where(*filters)
        .order_by(*SORT_EXPRESSIONS[sort])
        .limit(PRODUCTS_PER_PAGE)
        .offset((page - 1) * PRODUCTS_PER_PAGE)
    )
    items = tuple(
        PublicProductSummary(
            id=row.id,
            title=row.title,
            price=row.price,
            status=row.status,
            seller_username=row.username,
        )
        for row in db.session.execute(statement)
    )
    pages = ceil(total / PRODUCTS_PER_PAGE)
    has_prev = page > 1
    has_next = page < pages
    return PublicProductPage(
        items=items,
        page=page,
        per_page=PRODUCTS_PER_PAGE,
        total=total,
        pages=pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_num=page - 1 if has_prev else None,
        next_num=page + 1 if has_next else None,
    )


def get_public_product(product_id: str) -> PublicProductDetail | None:
    row = db.session.execute(
        db.select(
            Product.id,
            Product.title,
            Product.description,
            Product.price,
            Product.status,
            Product.created_at,
            User.username,
        )
        .select_from(Product)
        .join(User, Product.seller_id == User.id)
        .where(
            Product.id == product_id,
            Product.status.in_(PUBLIC_STATUSES),
            User.status == "active",
        )
    ).one_or_none()
    if row is None:
        return None
    return PublicProductDetail(
        id=row.id,
        title=row.title,
        description=row.description,
        price=row.price,
        status=row.status,
        seller_username=row.username,
        created_at=row.created_at,
    )


def list_owner_products(seller_id: str) -> tuple[OwnerProductView, ...]:
    statement = (
        db.select(
            Product.id,
            Product.title,
            Product.description,
            Product.price,
            Product.status,
            Product.created_at,
            Product.updated_at,
            Product.image_filename,
        )
        .where(Product.seller_id == seller_id)
        .order_by(Product.updated_at.desc(), Product.id.desc())
    )
    return tuple(
        OwnerProductView(
            id=row.id,
            title=row.title,
            description=row.description,
            price=row.price,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            has_image=row.image_filename is not None,
        )
        for row in db.session.execute(statement)
    )


def get_owner_editable_product(
    product_id: str, seller_id: str
) -> OwnerProductView | None:
    row = db.session.execute(
        db.select(
            Product.id,
            Product.title,
            Product.description,
            Product.price,
            Product.status,
            Product.created_at,
            Product.updated_at,
            Product.image_filename,
        ).where(
            Product.id == product_id,
            Product.seller_id == seller_id,
            Product.status.in_(OWNER_EDITABLE_STATUSES),
        )
    ).one_or_none()
    if row is None:
        return None
    return OwnerProductView(
        id=row.id,
        title=row.title,
        description=row.description,
        price=row.price,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        has_image=row.image_filename is not None,
    )


def create_product(
    *,
    seller_id: str,
    title: str,
    description: str,
    price: int,
    image: FileStorage,
) -> tuple[MutationResult, str | None, str | None]:
    try:
        stored = store_product_image(image)
    except ImageValidationError as error:
        return MutationResult.INVALID_STATE, None, str(error)

    product = Product(
        seller_id=seller_id,
        title=title,
        description=description,
        price=price,
        image_filename=stored.filename,
        status=CREATED_STATUS,
    )
    db.session.add(product)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        remove_product_image(stored.filename)
        return MutationResult.DATABASE_ERROR, None, None
    return MutationResult.OK, product.id, None


def update_product(
    *,
    product_id: str,
    seller_id: str,
    title: str,
    description: str,
    price: int,
    replacement_image: FileStorage | None,
) -> tuple[MutationResult, str | None]:
    product = db.session.execute(
        db.select(Product).where(
            Product.id == product_id,
            Product.seller_id == seller_id,
            Product.status.in_(OWNER_EDITABLE_STATUSES),
        )
    ).scalar_one_or_none()
    if product is None:
        return MutationResult.NOT_FOUND, None

    old_filename = product.image_filename
    new_filename = None
    if replacement_image is not None and replacement_image.filename:
        try:
            stored = store_product_image(replacement_image)
        except ImageValidationError as error:
            return MutationResult.INVALID_STATE, str(error)
        new_filename = stored.filename
        product.image_filename = new_filename

    product.title = title
    product.description = description
    product.price = price
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        if new_filename is not None:
            remove_product_image(new_filename)
        return MutationResult.DATABASE_ERROR, None

    if new_filename is not None and old_filename is not None:
        if not remove_product_image(old_filename):
            current_app.logger.warning(
                "An obsolete product image could not be removed after replacement"
            )
    return MutationResult.OK, None


def change_product_status(
    product_id: str, seller_id: str, requested_status: str
) -> MutationResult:
    product = db.session.execute(
        db.select(Product).where(
            Product.id == product_id,
            Product.seller_id == seller_id,
        )
    ).scalar_one_or_none()
    if product is None:
        return MutationResult.NOT_FOUND
    if product.status not in OWNER_EDITABLE_STATUSES:
        return MutationResult.INVALID_STATE
    if requested_status not in OWNER_EDITABLE_STATUSES:
        return MutationResult.INVALID_STATE
    product.status = requested_status
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return MutationResult.DATABASE_ERROR
    return MutationResult.OK


def soft_delete_product(product_id: str, seller_id: str) -> MutationResult:
    product = db.session.execute(
        db.select(Product).where(
            Product.id == product_id,
            Product.seller_id == seller_id,
        )
    ).scalar_one_or_none()
    if product is None or product.status == "deleted":
        return MutationResult.NOT_FOUND
    product.status = "deleted"
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return MutationResult.DATABASE_ERROR
    return MutationResult.OK


def get_image_access(
    product_id: str, authenticated_user_id: str | None
) -> ImageAccess | None:
    public_filename = db.session.execute(
        db.select(Product.image_filename)
        .select_from(Product)
        .join(User, Product.seller_id == User.id)
        .where(
            Product.id == product_id,
            Product.status.in_(PUBLIC_STATUSES),
            User.status == "active",
        )
    ).scalar_one_or_none()
    if public_filename is not None:
        return ImageAccess(filename=public_filename, is_public=True)
    if authenticated_user_id is None:
        return None

    owner_filename = db.session.execute(
        db.select(Product.image_filename).where(
            Product.id == product_id,
            Product.seller_id == authenticated_user_id,
        )
    ).scalar_one_or_none()
    if owner_filename is None:
        return None
    return ImageAccess(filename=owner_filename, is_public=False)

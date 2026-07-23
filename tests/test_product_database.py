from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Product


@pytest.mark.parametrize("price", [0, -1, 1_000_000_001])
def test_product_price_database_range_rejects_invalid_values(app, user_factory, price):
    seller = user_factory(username=f"price_invalid_{abs(price)}")
    with app.app_context():
        db.session.add(
            Product(
                seller_id=seller.id,
                title="가격 테스트",
                description="가격 범위 테스트",
                price=price,
                status="active",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize("price", [1, 1_000_000_000])
def test_product_price_database_range_accepts_boundaries(app, user_factory, price):
    seller = user_factory(username=f"price_valid_{price}")
    with app.app_context():
        product = Product(
            seller_id=seller.id,
            title="가격 테스트",
            description="가격 범위 테스트",
            price=price,
            status="active",
        )
        db.session.add(product)
        db.session.commit()
        assert product.price == price


def test_product_image_filename_unique_constraint(app, user_factory):
    seller = user_factory(username="unique_image")
    filename = f"{'a' * 32}.png"
    with app.app_context():
        db.session.add_all(
            (
                Product(
                    seller_id=seller.id,
                    title="첫 상품",
                    description="첫 설명",
                    price=100,
                    image_filename=filename,
                ),
                Product(
                    seller_id=seller.id,
                    title="둘째 상품",
                    description="둘째 설명",
                    price=200,
                    image_filename=filename,
                ),
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_nullable_image_filename_remains_allowed_for_legacy_rows(app, user_factory):
    seller = user_factory(username="nullable_image")
    with app.app_context():
        db.session.add_all(
            (
                Product(
                    seller_id=seller.id,
                    title="첫 상품",
                    description="첫 설명",
                    price=100,
                    image_filename=None,
                ),
                Product(
                    seller_id=seller.id,
                    title="둘째 상품",
                    description="둘째 설명",
                    price=200,
                    image_filename=None,
                ),
            )
        )
        db.session.commit()
        assert (
            db.session.execute(
                db.select(Product).where(Product.image_filename.is_(None))
            )
            .scalars()
            .all()
        )


def test_product_named_constraints_and_indexes_match_model(app):
    with app.app_context():
        inspector = inspect(db.engine)
        checks = {
            item["name"]: item for item in inspector.get_check_constraints("products")
        }
        uniques = {
            item["name"]: item for item in inspector.get_unique_constraints("products")
        }
        indexes = {item["name"]: item for item in inspector.get_indexes("products")}

    assert "ck_products_price_range" in checks
    assert "BETWEEN 1 AND 1000000000" in checks["ck_products_price_range"]["sqltext"]
    assert uniques["uq_products_image_filename"]["column_names"] == ["image_filename"]
    assert indexes["ix_products_public_status_created"]["column_names"] == [
        "status",
        "created_at",
    ]
    assert indexes["ix_products_seller_status_updated"]["column_names"] == [
        "seller_id",
        "status",
        "updated_at",
    ]
    assert indexes["ix_products_price"]["column_names"] == ["price"]


def test_no_product_upload_directory_exists_under_static():
    assert not Path("app/static/uploads").exists()
    assert not any(
        path.name == "products" and "upload" in path.as_posix().lower()
        for path in Path("app/static").rglob("*")
    )

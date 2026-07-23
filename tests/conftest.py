import re
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app import create_app
from app.extensions import db, limiter
from app.models import Product, User, Wallet


@pytest.fixture
def app(tmp_path):
    application = create_app(
        "testing",
        {
            "PRODUCT_UPLOAD_DIR": str(tmp_path / "uploads" / "products"),
        },
    )
    limiter.reset()
    with application.app_context():
        db.create_all()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()
    limiter.reset()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf_token():
    def extract(client, path: str) -> str:
        response = client.get(path)
        assert response.status_code == 200
        match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
        assert match is not None
        return match.group(1).decode()

    return extract


@pytest.fixture
def user_factory(app):
    def create(
        username: str = "alice",
        password: str = "valid-test-password-123",
        *,
        status: str = "active",
        role: str = "user",
        bio: str = "",
        balance: int = 100000,
    ) -> User:
        with app.app_context():
            user = User(username=username, status=status, role=role, bio=bio)
            user.set_password(password)
            wallet = Wallet(user=user, balance=balance)
            db.session.add_all((user, wallet))
            db.session.commit()
            user_id = user.id
        with app.app_context():
            return db.session.get(User, user_id)

    return create


@pytest.fixture
def login_client(csrf_token):
    def login(
        client,
        username: str = "alice",
        password: str = "valid-test-password-123",
    ):
        token = csrf_token(client, "/auth/login")
        return client.post(
            "/auth/login",
            data={"username": username, "password": password, "csrf_token": token},
        )

    return login


@pytest.fixture
def image_bytes():
    def create(
        image_format: str = "PNG",
        *,
        size: tuple[int, int] = (8, 8),
        color: tuple[int, ...] = (20, 80, 140),
        mode: str = "RGB",
        **save_options,
    ) -> bytes:
        output = BytesIO()
        Image.new(mode, size, color).save(output, format=image_format, **save_options)
        return output.getvalue()

    return create


@pytest.fixture
def product_factory(app, image_bytes):
    def create(
        seller: User,
        *,
        title: str = "테스트 상품",
        description: str = "안전한 테스트 상품 설명",
        price: int = 10000,
        status: str = "active",
        image_format: str = "PNG",
        image_filename: str | None = None,
        create_file: bool = True,
    ) -> Product:
        extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[image_format]
        filename = image_filename or f"{'a' * 32}.{extension}"
        with app.app_context():
            product = Product(
                seller_id=seller.id,
                title=title,
                description=description,
                price=price,
                status=status,
                image_filename=filename,
            )
            db.session.add(product)
            db.session.commit()
            product_id = product.id
            if create_file and filename is not None:
                upload_root = app.config["PRODUCT_UPLOAD_DIR"]
                root = Path(upload_root)
                root.mkdir(mode=0o700, parents=True, exist_ok=True)
                (root / filename).write_bytes(image_bytes(image_format))
                (root / filename).chmod(0o600)
        with app.app_context():
            return db.session.get(Product, product_id)

    return create

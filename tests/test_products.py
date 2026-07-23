import io
import re
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage

from app.extensions import db, limiter
from app.models import Product, User
from app.products import routes, services
from app.products.services import (
    MutationResult,
    PublicProductDetail,
    PublicProductPage,
    PublicProductSummary,
    create_product,
    update_product,
)


def multipart_image(image_bytes, image_format="PNG", filename=None):
    extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[image_format]
    return io.BytesIO(image_bytes(image_format)), filename or f"product.{extension}"


def create_form_data(token, image_bytes, **overrides):
    data = {
        "csrf_token": token,
        "title": " 안전한 상품 ",
        "description": " 안전한 설명 ",
        "price": "12000",
        "image": multipart_image(image_bytes),
    }
    data.update(overrides)
    return data


def login_user(client, user_factory, login_client, username="alice"):
    user = user_factory(username=username)
    response = login_client(client, username=username)
    assert response.status_code == 303
    return user


def test_public_products_and_create_routes_are_registered(app):
    rules = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}
    assert "/products" in rules
    assert "/products/new" in rules
    assert "/products/<uuid:product_id>" in rules
    assert "/products/<uuid:product_id>/image" in rules
    assert "/me/products" in rules
    assert rules["/me/products/<uuid:product_id>/delete"] == {
        "OPTIONS",
        "POST",
    }
    assert rules["/me/products/<uuid:product_id>/status"] == {
        "OPTIONS",
        "POST",
    }


@pytest.mark.parametrize(
    "path",
    [
        "/products/new",
        "/me/products",
        f"/me/products/{uuid4()}/edit",
    ],
)
def test_private_product_get_routes_require_authentication(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


@pytest.mark.parametrize(
    "path",
    [
        "/products/new",
        f"/me/products/{uuid4()}/edit",
        f"/me/products/{uuid4()}/status",
        f"/me/products/{uuid4()}/delete",
    ],
)
def test_product_mutations_without_csrf_are_rejected(
    client, user_factory, login_client, path
):
    login_user(client, user_factory, login_client)
    response = client.post(path, data={})
    assert response.status_code == 400


def test_get_create_renders_multipart_secure_form(client, user_factory, login_client):
    login_user(client, user_factory, login_client)
    response = client.get("/products/new")
    assert response.status_code == 200
    assert b"multipart/form-data" in response.data
    assert b'name="seller_id"' not in response.data
    assert b'name="status"' not in response.data
    assert response.headers["Cache-Control"] == "no-store, private"


@pytest.mark.parametrize(
    ("image_format", "input_filename", "stored_extension"),
    [
        ("JPEG", "original.jpeg", ".jpg"),
        ("PNG", "original.png", ".png"),
        ("WEBP", "original.webp", ".webp"),
    ],
)
def test_create_product_accepts_safe_image_and_forces_owner_and_active_status(
    app,
    client,
    csrf_token,
    user_factory,
    login_client,
    image_bytes,
    image_format,
    input_filename,
    stored_extension,
):
    user = login_user(client, user_factory, login_client)
    token = csrf_token(client, "/products/new")
    response = client.post(
        "/products/new",
        data=create_form_data(
            token,
            image_bytes,
            image=(
                io.BytesIO(image_bytes(image_format)),
                input_filename,
            ),
            seller_id=str(uuid4()),
            status="hidden",
            image_filename="attacker.png",
        ),
        content_type="multipart/form-data",
    )

    assert response.status_code == 303
    with app.app_context():
        product = db.session.execute(db.select(Product)).scalar_one()
        assert product.seller_id == user.id
        assert product.status == "active"
        assert product.title == "안전한 상품"
        assert product.description == "안전한 설명"
        assert product.image_filename.endswith(stored_extension)
        assert re.fullmatch(r"[0-9a-f]{32}\.(?:jpg|png|webp)", product.image_filename)
        assert (
            Path(app.config["PRODUCT_UPLOAD_DIR"]) / product.image_filename
        ).is_file()


@pytest.mark.parametrize(
    ("overrides", "expected_fragment"),
    [
        ({"title": "   "}, None),
        ({"title": "x" * 101}, None),
        ({"description": "   "}, None),
        ({"description": "x" * 2001}, None),
        ({"price": "0"}, None),
        ({"price": "-1"}, None),
        ({"price": "1.5"}, None),
        ({"price": "1000000001"}, None),
        ({"image": (io.BytesIO(b""), "")}, None),
        (
            {"image": (io.BytesIO(b"not an image"), "attack.png")},
            b"JPEG",
        ),
    ],
)
def test_create_rejects_invalid_fields_and_images(
    client,
    csrf_token,
    user_factory,
    login_client,
    image_bytes,
    overrides,
    expected_fragment,
):
    login_user(client, user_factory, login_client)
    token = csrf_token(client, "/products/new")
    data = create_form_data(token, image_bytes)
    data.update(overrides)
    response = client.post(
        "/products/new", data=data, content_type="multipart/form-data"
    )
    assert response.status_code == 400
    if expected_fragment:
        assert expected_fragment in response.data


def test_create_database_failure_rolls_back_row_and_new_file(
    app, user_factory, image_bytes, monkeypatch
):
    user = user_factory()
    storage = FileStorage(stream=io.BytesIO(image_bytes("PNG")), filename="product.png")
    with app.app_context():
        monkeypatch.setattr(
            db.session, "commit", lambda: (_ for _ in ()).throw(SQLAlchemyError())
        )
        result, product_id, error = create_product(
            seller_id=user.id,
            title="상품",
            description="설명",
            price=100,
            image=storage,
        )
        assert result is MutationResult.DATABASE_ERROR
        assert product_id is None
        assert error is None
        assert db.session.execute(db.select(Product)).all() == []
        root = Path(app.config["PRODUCT_UPLOAD_DIR"])
        assert list(root.iterdir()) == []


def test_create_rate_limit_is_per_authenticated_user(
    client, csrf_token, user_factory, login_client
):
    login_user(client, user_factory, login_client)
    token = csrf_token(client, "/products/new")
    for _index in range(10):
        response = client.post(
            "/products/new",
            data={"csrf_token": token, "title": ""},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400
    response = client.post(
        "/products/new",
        data={"csrf_token": token},
        content_type="multipart/form-data",
    )
    assert response.status_code == 429


@pytest.mark.parametrize("status", ["active", "sold"])
def test_public_list_and_detail_show_active_and_sold(
    client, user_factory, product_factory, status
):
    seller = user_factory(username=f"seller_{status}")
    product = product_factory(seller, status=status, title=f"{status} 상품")
    list_response = client.get("/products")
    detail_response = client.get(f"/products/{product.id}")
    assert list_response.status_code == 200
    assert f"{status} 상품".encode() in list_response.data
    assert detail_response.status_code == 200
    assert seller.username.encode() in detail_response.data


@pytest.mark.parametrize("status", ["hidden", "deleted"])
def test_hidden_and_deleted_products_are_not_public(
    client, user_factory, product_factory, status
):
    seller = user_factory(username=f"seller_{status}")
    product = product_factory(seller, status=status, title=f"{status} 상품")
    assert f"{status} 상품".encode() not in client.get("/products").data
    assert client.get(f"/products/{product.id}").status_code == 404
    assert client.get(f"/products/{product.id}/image").status_code == 404


def test_dormant_seller_product_is_not_public(client, user_factory, product_factory):
    seller = user_factory(username="dormant_seller", status="dormant")
    product = product_factory(seller, title="비공개 상품")
    assert b"\xeb\xb9\x84\xea\xb3\xb5\xea\xb0\x9c" not in client.get("/products").data
    assert client.get(f"/products/{product.id}").status_code == 404
    assert client.get(f"/products/{product.id}/image").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        f"/products/{uuid4()}",
        f"/products/{uuid4()}/image",
        "/products/not-a-uuid",
        "/products/not-a-uuid/image",
    ],
)
def test_missing_and_malformed_public_product_ids_are_404(client, path):
    assert client.get(path).status_code == 404


def test_public_html_escapes_content_and_exposes_only_public_identity(
    client, user_factory, product_factory
):
    seller = user_factory(
        username="seller_safe",
        role="admin",
        balance=987654321,
    )
    product = product_factory(
        seller,
        title="<script>alert(1)</script>",
        description="<img src=x onerror=alert(2)>",
    )
    response = client.get(f"/products/{product.id}")
    html = response.get_data(as_text=True)

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(2)&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert seller.username in html
    assert seller.id not in html
    assert seller.password_hash not in html
    assert "987654321" not in html
    assert product.seller_id not in html
    assert product.image_filename not in html
    assert f"/products/{product.id}/image" in html


def test_public_templates_receive_dtos_not_orm_objects(
    app, client, user_factory, product_factory, monkeypatch
):
    seller = user_factory(username="projection_seller")
    product = product_factory(seller)
    captured = []
    original = routes.render_template

    def capture(template, **context):
        captured.append((template, context))
        return original(template, **context)

    monkeypatch.setattr(routes, "render_template", capture)
    assert client.get("/products").status_code == 200
    assert client.get(f"/products/{product.id}").status_code == 200

    page = captured[0][1]["page"]
    detail = captured[1][1]["product"]
    assert isinstance(page, PublicProductPage)
    assert all(isinstance(item, PublicProductSummary) for item in page.items)
    assert isinstance(detail, PublicProductDetail)
    for _template, context in captured:
        assert not any(isinstance(value, (Product, User)) for value in context.values())


def test_public_select_projection_does_not_select_private_columns(
    app, client, user_factory, product_factory
):
    seller = user_factory(username="sql_projection")
    product = product_factory(seller)
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", capture)
    try:
        assert client.get("/products").status_code == 200
        assert client.get(f"/products/{product.id}").status_code == 200
    finally:
        with app.app_context():
            event.remove(db.engine, "before_cursor_execute", capture)

    product_selects = [
        statement.lower()
        for statement in statements
        if "from products" in statement.lower()
    ]
    assert product_selects
    for statement in product_selects:
        projection = statement.split("from products", 1)[0]
        assert "products.seller_id" not in projection
        assert "products.image_filename" not in projection
        assert "users.id" not in projection
        assert "users.password_hash" not in projection
        assert "users.role" not in projection
        assert "users.status" not in projection
        assert "users.auth_version" not in projection


@pytest.mark.parametrize(
    ("image_format", "expected_mime", "extension"),
    [
        ("JPEG", "image/jpeg", ".jpg"),
        ("PNG", "image/png", ".png"),
        ("WEBP", "image/webp", ".webp"),
    ],
)
def test_public_image_response_has_safe_headers(
    client,
    user_factory,
    product_factory,
    image_format,
    expected_mime,
    extension,
):
    seller = user_factory(username=f"image_{image_format.lower()}")
    product = product_factory(seller, image_format=image_format)
    response = client.get(f"/products/{product.id}/image")
    assert response.status_code == 200
    assert response.mimetype == expected_mime
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Disposition"] == (
        f'inline; filename="product{extension}"'
    )
    assert response.headers["Cache-Control"] == "public, max-age=300"
    assert product.image_filename not in response.headers["Content-Disposition"]


def test_unsafe_symlink_and_missing_product_images_return_404(
    app, client, user_factory, product_factory, image_bytes, tmp_path
):
    seller = user_factory(username="broken_images")
    unsafe = product_factory(
        seller,
        image_filename="../outside.png",
        create_file=False,
    )
    missing = product_factory(
        seller,
        image_filename=f"{'b' * 32}.png",
        create_file=False,
    )
    symlink = product_factory(
        seller,
        image_filename=f"{'c' * 32}.png",
        create_file=False,
    )
    outside = tmp_path / "outside.png"
    outside.write_bytes(image_bytes("PNG"))
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    (root / symlink.image_filename).symlink_to(outside)
    for product in (unsafe, missing, symlink):
        assert client.get(f"/products/{product.id}/image").status_code == 404


@pytest.mark.parametrize("status", ["hidden", "deleted"])
def test_owner_can_read_own_nonpublic_image_but_other_user_cannot(
    client,
    user_factory,
    product_factory,
    login_client,
    status,
):
    owner = user_factory(username=f"owner_{status}")
    product = product_factory(owner, status=status)
    login_client(client, username=owner.username)
    owner_response = client.get(f"/products/{product.id}/image")
    assert owner_response.status_code == 200
    assert owner_response.headers["Cache-Control"] == "no-store, private"

    other_client = client.application.test_client()
    user_factory(username=f"other_{status}")
    login_client(other_client, username=f"other_{status}")
    assert other_client.get(f"/products/{product.id}/image").status_code == 404


def test_owner_list_includes_all_own_statuses_and_no_other_products(
    client, user_factory, product_factory, login_client
):
    owner = user_factory(username="owner_list")
    other = user_factory(username="other_list")
    for index, status in enumerate(("active", "sold", "hidden", "deleted")):
        product_factory(
            owner,
            status=status,
            title=f"내 상품 {index}",
            image_filename=f"{index + 1:032x}.png",
        )
    product_factory(
        other,
        title="다른 사용자 상품",
        image_filename=f"{99:032x}.png",
    )
    login_client(client, username=owner.username)
    response = client.get("/me/products")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"
    for index in range(4):
        assert f"내 상품 {index}" in html
    assert "다른 사용자 상품" not in html


def test_owner_can_edit_fields_without_changing_owner_status_or_image(
    app,
    client,
    csrf_token,
    user_factory,
    product_factory,
    login_client,
):
    owner = user_factory(username="edit_owner")
    product = product_factory(owner, status="sold")
    old_filename = product.image_filename
    login_client(client, username=owner.username)
    token = csrf_token(client, f"/me/products/{product.id}/edit")
    response = client.post(
        f"/me/products/{product.id}/edit",
        data={
            "csrf_token": token,
            "title": " 변경 상품 ",
            "description": " 변경 설명 ",
            "price": "50000",
            "seller_id": str(uuid4()),
            "status": "active",
            "image_filename": "attacker.png",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 303
    with app.app_context():
        changed = db.session.get(Product, product.id)
        assert changed.title == "변경 상품"
        assert changed.description == "변경 설명"
        assert changed.price == 50000
        assert changed.seller_id == owner.id
        assert changed.status == "sold"
        assert changed.image_filename == old_filename


def test_image_replacement_commits_then_removes_old_file(
    app,
    client,
    csrf_token,
    user_factory,
    product_factory,
    login_client,
    image_bytes,
):
    owner = user_factory(username="replace_owner")
    product = product_factory(owner)
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    old_path = root / product.image_filename
    login_client(client, username=owner.username)
    token = csrf_token(client, f"/me/products/{product.id}/edit")
    response = client.post(
        f"/me/products/{product.id}/edit",
        data={
            "csrf_token": token,
            "title": "교체 상품",
            "description": "교체 설명",
            "price": "20000",
            "image": multipart_image(image_bytes, "JPEG"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 303
    with app.app_context():
        changed = db.session.get(Product, product.id)
        new_path = root / changed.image_filename
        assert changed.image_filename != product.image_filename
    assert new_path.is_file()
    assert not old_path.exists()


def test_image_replacement_database_failure_removes_new_and_keeps_old(
    app, user_factory, product_factory, image_bytes, monkeypatch
):
    owner = user_factory(username="replace_failure")
    product = product_factory(owner)
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    old_path = root / product.image_filename
    storage = FileStorage(
        stream=io.BytesIO(image_bytes("JPEG")), filename="replacement.jpg"
    )
    with app.app_context():
        monkeypatch.setattr(
            db.session, "commit", lambda: (_ for _ in ()).throw(SQLAlchemyError())
        )
        result, error = update_product(
            product_id=product.id,
            seller_id=owner.id,
            title="변경",
            description="변경 설명",
            price=30000,
            replacement_image=storage,
        )
        assert result is MutationResult.DATABASE_ERROR
        assert error is None
        assert old_path.is_file()
        assert list(root.iterdir()) == [old_path]


@pytest.mark.parametrize("status", ["hidden", "deleted"])
def test_hidden_and_deleted_product_edit_is_404(
    client,
    user_factory,
    product_factory,
    login_client,
    status,
):
    owner = user_factory(username=f"blocked_edit_{status}")
    product = product_factory(owner, status=status)
    login_client(client, username=owner.username)
    assert client.get(f"/me/products/{product.id}/edit").status_code == 404


def test_other_user_cannot_edit_change_status_or_delete(
    client,
    csrf_token,
    user_factory,
    product_factory,
    login_client,
):
    owner = user_factory(username="idor_owner")
    product = product_factory(owner)
    user_factory(username="idor_attacker")
    login_client(client, username="idor_attacker")
    token = csrf_token(client, "/me/products")

    assert client.get(f"/me/products/{product.id}/edit").status_code == 404
    assert (
        client.post(
            f"/me/products/{product.id}/status",
            data={"csrf_token": token, "status": "sold"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/me/products/{product.id}/delete",
            data={"csrf_token": token},
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    ("starting", "requested"),
    [
        ("active", "sold"),
        ("sold", "active"),
        ("active", "active"),
        ("sold", "sold"),
    ],
)
def test_owner_status_transitions_are_allowlisted_and_idempotent(
    app,
    client,
    csrf_token,
    user_factory,
    product_factory,
    login_client,
    starting,
    requested,
):
    owner = user_factory(username=f"transition_{starting}_{requested}")
    product = product_factory(owner, status=starting)
    login_client(client, username=owner.username)
    token = csrf_token(client, "/me/products")
    response = client.post(
        f"/me/products/{product.id}/status",
        data={"csrf_token": token, "status": requested},
    )
    assert response.status_code == 303
    with app.app_context():
        assert db.session.get(Product, product.id).status == requested


@pytest.mark.parametrize("starting", ["hidden", "deleted"])
def test_owner_cannot_restore_nonpublic_moderation_states(
    client,
    csrf_token,
    user_factory,
    product_factory,
    login_client,
    starting,
):
    owner = user_factory(username=f"restore_{starting}")
    product = product_factory(owner, status=starting)
    login_client(client, username=owner.username)
    token = csrf_token(client, "/me/products")
    response = client.post(
        f"/me/products/{product.id}/status",
        data={"csrf_token": token, "status": "active"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize("requested", ["hidden", "deleted", "admin", ""])
def test_status_form_rejects_non_allowlisted_values(
    client,
    csrf_token,
    user_factory,
    product_factory,
    login_client,
    requested,
):
    owner = user_factory(username=f"invalid_status_{requested or 'empty'}")
    product = product_factory(owner)
    login_client(client, username=owner.username)
    token = csrf_token(client, "/me/products")
    response = client.post(
        f"/me/products/{product.id}/status",
        data={"csrf_token": token, "status": requested},
    )
    assert response.status_code == 400


def test_soft_delete_retains_row_and_file_and_immediately_blocks_public_access(
    app,
    client,
    csrf_token,
    user_factory,
    product_factory,
    login_client,
):
    owner = user_factory(username="delete_owner")
    product = product_factory(owner)
    image_path = Path(app.config["PRODUCT_UPLOAD_DIR"]) / product.image_filename
    login_client(client, username=owner.username)
    token = csrf_token(client, "/me/products")
    response = client.post(
        f"/me/products/{product.id}/delete",
        data={"csrf_token": token},
    )
    assert response.status_code == 303
    with app.app_context():
        assert db.session.get(Product, product.id).status == "deleted"
    assert image_path.is_file()
    other_client = app.test_client()
    assert other_client.get(f"/products/{product.id}").status_code == 404
    assert other_client.get(f"/products/{product.id}/image").status_code == 404


def test_get_status_and_delete_are_method_not_allowed(
    client, user_factory, product_factory, login_client
):
    owner = user_factory(username="method_owner")
    product = product_factory(owner)
    login_client(client, username=owner.username)
    assert client.get(f"/me/products/{product.id}/status").status_code == 405
    assert client.get(f"/me/products/{product.id}/delete").status_code == 405


def test_product_mutation_rate_limit(client, csrf_token, user_factory, login_client):
    login_user(client, user_factory, login_client, username="rate_mutation")
    token = csrf_token(client, "/me/products")
    unknown_id = uuid4()
    for _index in range(30):
        response = client.post(
            f"/me/products/{unknown_id}/delete",
            data={"csrf_token": token},
        )
        assert response.status_code == 404
    assert (
        client.post(
            f"/me/products/{unknown_id}/delete",
            data={"csrf_token": token},
        ).status_code
        == 429
    )


def seed_search_products(user_factory, product_factory):
    seller = user_factory(username="search_seller")
    products = [
        product_factory(
            seller,
            title="Alpha 100%_literal",
            description="red apple",
            price=100,
            status="active",
            image_filename=f"{1:032x}.png",
        ),
        product_factory(
            seller,
            title="Beta",
            description="blue berry",
            price=200,
            status="sold",
            image_filename=f"{2:032x}.png",
        ),
        product_factory(
            seller,
            title="Gamma",
            description="green apple",
            price=300,
            status="hidden",
            image_filename=f"{3:032x}.png",
        ),
        product_factory(
            seller,
            title="Delta",
            description="red berry",
            price=400,
            status="deleted",
            image_filename=f"{4:032x}.png",
        ),
    ]
    return products


@pytest.mark.parametrize(
    ("query", "visible", "hidden"),
    [
        ("q=Alpha", "Alpha", "Beta"),
        ("q=blue", "Beta", "Alpha"),
        ("q=100%25_literal", "Alpha", "Beta"),
        ("q=%25", "Alpha", "Beta"),
        ("q=_", "Alpha", "Beta"),
        ("q=%27%20OR%201%3D1--", None, "Alpha"),
        ("status=active", "Alpha", "Beta"),
        ("status=sold", "Beta", "Alpha"),
        ("min_price=150", "Beta", "Alpha"),
        ("max_price=150", "Alpha", "Beta"),
        ("min_price=100&max_price=200", "Alpha", "Gamma"),
    ],
)
def test_public_search_filters_are_parameterized_and_literal(
    client, user_factory, product_factory, query, visible, hidden
):
    seed_search_products(user_factory, product_factory)
    response = client.get(f"/products?{query}")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    if visible is not None:
        assert visible in html
    assert hidden not in html
    assert "Gamma" not in html
    assert "Delta" not in html


@pytest.mark.parametrize(
    "query",
    [
        "q=" + "x" * 101,
        "status=hidden",
        "status=deleted",
        "status=invalid",
        "sort=price%20desc",
        "sort=invalid",
        "min_price=0",
        "max_price=1000000001",
        "min_price=200&max_price=100",
        "page=0",
        "page=1001",
        "page=not-a-number",
    ],
)
def test_invalid_search_parameters_return_400(client, query):
    assert client.get(f"/products?{query}").status_code == 400


def test_search_sort_allowlist_and_stable_tie_breakers(
    app, user_factory, product_factory
):
    seller = user_factory(username="sort_seller")
    older = product_factory(
        seller,
        title="Zulu",
        price=200,
        image_filename=f"{11:032x}.png",
    )
    newer = product_factory(
        seller,
        title="Alpha",
        price=100,
        image_filename=f"{12:032x}.png",
    )
    with app.app_context():
        older_row = db.session.get(Product, older.id)
        newer_row = db.session.get(Product, newer.id)
        older_row.created_at = older_row.created_at.replace(year=2020)
        newer_row.created_at = newer_row.created_at.replace(year=2021)
        db.session.commit()
        expected = {
            "newest": [newer.id, older.id],
            "oldest": [older.id, newer.id],
            "price_low": [newer.id, older.id],
            "price_high": [older.id, newer.id],
            "title": [newer.id, older.id],
        }
        for sort, ids in expected.items():
            page = services.search_public_products(
                query=None,
                status="all",
                min_price=None,
                max_price=None,
                sort=sort,
                page=1,
            )
            assert [item.id for item in page.items] == ids


def test_search_uses_fixed_limit_and_preserves_filters_in_pagination(
    client, user_factory, product_factory
):
    seller = user_factory(username="pagination_seller")
    for index in range(21):
        product_factory(
            seller,
            title=f"Page item {index:02d}",
            price=100 + index,
            image_filename=f"{index + 100:032x}.png",
        )
    response = client.get(
        "/products?q=Page&status=active&min_price=100&max_price=999&"
        "sort=price_low&per_page=100"
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert html.count('class="product-card"') == 20
    assert "Page item 20" not in html
    assert "q=Page" in html
    assert "status=active" in html
    assert "min_price=100" in html
    assert "max_price=999" in html
    assert "sort=price_low" in html
    assert "page=2" in html


def test_empty_search_results_are_normal(client):
    response = client.get("/products?q=no-results")
    assert response.status_code == 200
    assert "조건에 맞는 상품이 없습니다." in response.get_data(as_text=True)


def test_search_rate_limit(client):
    limiter.reset()
    for _index in range(60):
        assert client.get("/products").status_code == 200
    assert client.get("/products").status_code == 429


def test_413_upload_error_is_generic_and_does_not_disclose_filename(
    app, client, csrf_token, user_factory, login_client
):
    login_user(client, user_factory, login_client, username="large_upload")
    token = csrf_token(client, "/products/new")
    secret_filename = "private-original-name.png"
    response = client.post(
        "/products/new",
        data={
            "csrf_token": token,
            "title": "상품",
            "description": "설명",
            "price": "1",
            "image": (io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)), secret_filename),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 413
    assert secret_filename.encode() not in response.data
    assert str(app.config["PRODUCT_UPLOAD_DIR"]).encode() not in response.data
    assert b"RequestEntityTooLarge" not in response.data


def test_database_error_response_is_generic(
    app,
    client,
    csrf_token,
    user_factory,
    login_client,
    image_bytes,
    monkeypatch,
):
    login_user(client, user_factory, login_client, username="db_error")
    token = csrf_token(client, "/products/new")
    monkeypatch.setattr(
        routes,
        "create_product",
        lambda **_kwargs: (MutationResult.DATABASE_ERROR, None, None),
    )
    response = client.post(
        "/products/new",
        data=create_form_data(token, image_bytes),
        content_type="multipart/form-data",
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 409
    for secret in (
        "IntegrityError",
        "ck_products_price_range",
        "INSERT INTO",
        str(app.config["PRODUCT_UPLOAD_DIR"]),
        "Traceback",
    ):
        assert secret not in body


@pytest.mark.parametrize(
    "path",
    [
        "/products",
        f"/products/{uuid4()}",
        "/products/new",
        "/me/products",
    ],
)
def test_product_responses_keep_security_headers(
    client, user_factory, login_client, path
):
    if path in {"/products/new", "/me/products"}:
        login_user(client, user_factory, login_client, username="headers_user")
    response = client.get(path)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_search_service_source_has_no_dynamic_sql_or_unbounded_all():
    source = Path("app/products/services.py").read_text(encoding="utf-8")
    assert "text(" not in source
    assert "order_by(sort" not in source
    assert ".all()" not in source
    assert "SORT_EXPRESSIONS" in source

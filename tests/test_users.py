from dataclasses import FrozenInstanceError, fields

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import User
from app.users.services import (
    PublicUserPage,
    PublicUserView,
    get_public_user,
    search_public_users,
)


def capture_sql(engine, operation):
    statements = []

    def record_statement(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ):
        statements.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        result = operation()
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
    return result, statements


def selected_columns(statement):
    select_clause, separator, _remainder = statement.partition(" FROM ")
    assert separator
    assert select_clause.startswith("SELECT ")
    return tuple(
        column.strip() for column in select_clause.removeprefix("SELECT ").split(",")
    )


def test_public_user_view_has_exact_immutable_field_allowlist():
    view = PublicUserView(username="alice", bio="공개 소개")

    assert tuple(field.name for field in fields(PublicUserView)) == ("username", "bio")
    for forbidden_attribute in (
        "id",
        "password_hash",
        "role",
        "status",
        "auth_version",
        "balance",
    ):
        assert not hasattr(view, forbidden_attribute)
    assert not hasattr(view, "__dict__")
    with pytest.raises(FrozenInstanceError):
        view.bio = "changed"


def test_public_user_list_executes_username_bio_only_page_projection(app, user_factory):
    user_factory(username="alice", bio="공개 소개")
    user_factory(username="sleepy", status="dormant", bio="비공개 소개")

    with app.app_context():
        page, statements = capture_sql(
            db.engine,
            lambda: search_public_users("ali", page=1, per_page=20),
        )

    page_select = next(statement for statement in statements if " LIMIT " in statement)
    assert selected_columns(page_select) == ("users.username", "users.bio")
    assert "WHERE users.status = ?" in page_select
    assert "ORDER BY users.username ASC, users.id ASC" in page_select
    assert "users.id" not in selected_columns(page_select)
    assert page.items == (PublicUserView(username="alice", bio="공개 소개"),)
    assert (page.page, page.per_page, page.total, page.pages) == (1, 20, 1, 1)


def test_public_profile_executes_username_bio_only_projection(app, user_factory):
    user_factory(username="alice", bio="공개 소개")

    with app.app_context():
        public_user, statements = capture_sql(
            db.engine,
            lambda: get_public_user("alice"),
        )

    assert len(statements) == 1
    assert selected_columns(statements[0]) == ("users.username", "users.bio")
    assert "users.status = ?" in statements[0]
    assert public_user == PublicUserView(username="alice", bio="공개 소개")


def test_public_routes_pass_view_models_instead_of_user_orm(
    client, user_factory, monkeypatch
):
    user_factory(username="alice", bio="공개 소개")
    rendered_contexts = {}

    def capture_template(template_name, **context):
        rendered_contexts[template_name] = context
        return "captured"

    monkeypatch.setattr("app.users.routes.render_template", capture_template)

    assert client.get("/users").status_code == 200
    assert client.get("/users/alice").status_code == 200

    list_context = rendered_contexts["users/index.html"]
    profile_context = rendered_contexts["users/profile.html"]
    assert set(list_context) == {"form", "pagination"}
    assert isinstance(list_context["pagination"], PublicUserPage)
    assert all(
        isinstance(item, PublicUserView) for item in list_context["pagination"].items
    )
    assert not any(isinstance(value, User) for value in list_context.values())
    assert set(profile_context) == {"profile_user"}
    assert isinstance(profile_context["profile_user"], PublicUserView)
    assert not any(isinstance(value, User) for value in profile_context.values())


def test_user_list_is_public_and_only_contains_active_public_fields(
    client, user_factory
):
    active = user_factory(
        username="alice",
        bio="공개 소개",
        role="admin",
        balance=987654,
    )
    dormant = user_factory(
        username="sleepy",
        status="dormant",
        bio="비공개 소개",
    )

    response = client.get("/users")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "alice" in body
    assert "공개 소개" in body
    assert "sleepy" not in body
    assert "비공개 소개" not in body
    assert active.id not in body
    assert dormant.id not in body
    assert active.password_hash not in body
    assert "987654" not in body
    assert "auth_version" not in body
    assert "role" not in body
    assert "status" not in body


def test_user_search_matches_username_substring_and_escapes_wildcards(
    client, user_factory
):
    user_factory(username="alice")
    user_factory(username="malice")
    user_factory(username="bobby")
    user_factory(username="under_score")
    user_factory(username="underXscore")

    response = client.get("/users?q=lic")
    literal_underscore_response = client.get("/users?q=under_score")
    literal_percent_response = client.get("/users?q=%25")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "alice" in body and "malice" in body
    assert "bobby" not in body
    literal_underscore_body = literal_underscore_response.get_data(as_text=True)
    assert "under_score" in literal_underscore_body
    assert "underXscore" not in literal_underscore_body
    assert "검색 결과가 없습니다." in literal_percent_response.get_data(as_text=True)


def test_user_search_with_no_matches_returns_normal_empty_page(client, user_factory):
    user_factory(username="alice")

    response = client.get("/users?q=missing")

    assert response.status_code == 200
    assert "검색 결과가 없습니다." in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "query", ["q=" + "a" * 33, "page=0", "page=-1", "page=1001", "page=nope"]
)
def test_user_search_rejects_invalid_query(client, query):
    response = client.get(f"/users?{query}")

    assert response.status_code == 400
    assert b"Traceback" not in response.data


def test_user_list_uses_fixed_twenty_item_page(client, user_factory):
    for number in range(25):
        user_factory(username=f"user{number:02d}")

    first_page = client.get("/users?per_page=1000")
    second_page = client.get("/users?page=2&per_page=1")

    first_body = first_page.get_data(as_text=True)
    second_body = second_page.get_data(as_text=True)
    assert first_page.status_code == 200
    assert sum(f"user{number:02d}" in first_body for number in range(25)) == 20
    assert sum(f"user{number:02d}" in second_body for number in range(25)) == 5


def test_user_list_order_is_stable(client, user_factory):
    for username in ("charlie", "alice", "bobby"):
        user_factory(username=username)

    body = client.get("/users").get_data(as_text=True)

    assert body.index("alice") < body.index("bobby") < body.index("charlie")


def test_user_search_rate_limit(client):
    responses = [client.get("/users") for _ in range(61)]

    assert all(response.status_code == 200 for response in responses[:60])
    assert responses[60].status_code == 429


def test_active_public_profile_only_renders_username_and_bio(client, user_factory):
    user = user_factory(
        username="alice",
        bio="공개 소개",
        role="admin",
        balance=987654,
    )

    response = client.get("/users/alice")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "alice" in body
    assert "공개 소개" in body
    assert user.id not in body
    assert user.password_hash not in body
    assert "987654" not in body
    assert "auth_version" not in body
    assert "role" not in body
    assert "status" not in body


def test_dormant_and_missing_public_profiles_share_404_response(client, user_factory):
    user_factory(username="sleepy", status="dormant")

    dormant = client.get("/users/sleepy")
    missing = client.get("/users/missing")

    assert dormant.status_code == missing.status_code == 404
    assert dormant.data == missing.data


def test_me_requires_authentication(client):
    response = client.get("/me")

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/login")


def test_me_displays_only_current_user_data_and_virtual_point_notice(
    client, user_factory, login_client
):
    user_factory(username="alice", bio="내 소개", balance=123456)
    user_factory(username="bobby", bio="다른 사람 소개", balance=987654)
    assert login_client(client).status_code == 303

    response = client.get("/me?user_id=ignored")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "alice" in body
    assert "내 소개" in body
    assert "123456" in body
    assert "다른 사람 소개" not in body
    assert "987654" not in body
    assert "실제 금융 자산이 아닙니다" in body
    assert response.headers["Cache-Control"] == "no-store, private"


def test_bio_change_requires_csrf(client, user_factory, login_client):
    user_factory()
    assert login_client(client).status_code == 303

    response = client.post("/me/bio", data={"bio": "새 소개"})

    assert response.status_code == 400


def test_bio_change_updates_only_current_user(
    app, client, user_factory, login_client, csrf_token
):
    current = user_factory(username="alice", bio="이전 소개")
    other = user_factory(username="bobby", bio="다른 소개")
    assert login_client(client).status_code == 303
    token = csrf_token(client, "/me")

    response = client.post(
        "/me/bio",
        data={"bio": "새 소개", "user_id": other.id, "csrf_token": token},
    )

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/me")
    with app.app_context():
        assert db.session.get(User, current.id).bio == "새 소개"
        assert db.session.get(User, other.id).bio == "다른 소개"


def test_empty_bio_is_allowed(app, client, user_factory, login_client, csrf_token):
    user = user_factory(bio="기존 소개")
    assert login_client(client).status_code == 303
    token = csrf_token(client, "/me")

    response = client.post("/me/bio", data={"bio": "", "csrf_token": token})

    assert response.status_code == 303
    with app.app_context():
        assert db.session.get(User, user.id).bio == ""


def test_bio_longer_than_500_characters_is_rejected(
    app, client, user_factory, login_client, csrf_token
):
    user = user_factory(bio="unchanged")
    assert login_client(client).status_code == 303
    token = csrf_token(client, "/me")

    response = client.post("/me/bio", data={"bio": "a" * 501, "csrf_token": token})

    assert response.status_code == 400
    with app.app_context():
        assert db.session.get(User, user.id).bio == "unchanged"


def test_stored_bio_is_autoescaped_on_me_and_public_profile(
    client, user_factory, login_client, csrf_token
):
    payload = '<script>alert("stored-xss")</script>'
    user_factory()
    assert login_client(client).status_code == 303
    token = csrf_token(client, "/me")
    assert (
        client.post("/me/bio", data={"bio": payload, "csrf_token": token}).status_code
        == 303
    )

    me_response = client.get("/me")
    public_response = client.get("/users/alice")

    for response in (me_response, public_response):
        body = response.get_data(as_text=True)
        assert payload not in body
        assert "&lt;script&gt;" in body
        assert "&lt;/script&gt;" in body


def test_bio_database_error_is_rolled_back_and_hidden(
    app, client, user_factory, login_client, csrf_token, monkeypatch
):
    user = user_factory(bio="original")
    assert login_client(client).status_code == 303
    token = csrf_token(client, "/me")

    def fail_commit():
        raise SQLAlchemyError("private database detail")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = client.post("/me/bio", data={"bio": "changed", "csrf_token": token})

    assert response.status_code == 400
    assert b"private database detail" not in response.data
    assert b"Traceback" not in response.data
    with app.app_context():
        assert db.session.get(User, user.id).bio == "original"


def test_bio_change_rate_limit_is_per_user(
    client, user_factory, login_client, csrf_token
):
    user_factory()
    assert login_client(client).status_code == 303
    token = csrf_token(client, "/me")
    data = {"bio": "rate limited", "csrf_token": token}
    responses = [client.post("/me/bio", data=data) for _ in range(31)]

    assert all(response.status_code == 303 for response in responses[:30])
    assert responses[30].status_code == 429


@pytest.mark.parametrize(
    "path",
    [
        "/auth/register",
        "/auth/login",
        "/users",
        "/users/missing",
    ],
)
def test_auth_and_user_responses_keep_security_headers(client, path):
    response = client.get(path)

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_templates_do_not_use_inline_scripts_styles_or_safe_filter():
    import re
    from pathlib import Path

    templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("app/templates").rglob("*.html")
    )

    script_tags = re.findall(r"<script\b[^>]*>", templates)
    assert script_tags
    assert all(" src=" in tag for tag in script_tags)
    assert "style=" not in templates
    assert "|safe" not in templates
    assert "Markup" not in templates

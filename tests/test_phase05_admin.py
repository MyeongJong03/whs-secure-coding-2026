import re
from html import unescape
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.admin import routes
from app.admin.services import (
    AdminMutationResult,
    change_message_visibility,
    change_product_status,
    change_user_status,
    decide_report,
)
from app.admin.views import (
    AdminAuditLogPage,
    AdminMessagePage,
    AdminProductPage,
    AdminReportPage,
    AdminTransferPage,
    AdminUserPage,
)
from app.audit.policy import safe_details_for_display, validate_audit_details
from app.audit.services import add_audit_log
from app.extensions import db, socketio
from app.models import (
    AuditLog,
    ChatMessage,
    DirectConversation,
    Product,
    Report,
    Transfer,
    User,
    Wallet,
)


PASSWORD = "valid-test-password-123"


def login(client, login_client, username):
    assert login_client(client, username=username, password=PASSWORD).status_code == 303


def csrf_from(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return (
        re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
        .group(1)
        .decode()
    )


def admin_login(client, user_factory, login_client, username="administrator"):
    admin = user_factory(username, role="admin")
    login(client, login_client, username)
    return admin


ADMIN_LIST_ROUTES = (
    "/admin",
    "/admin/users",
    "/admin/products",
    "/admin/reports",
    "/admin/messages",
    "/admin/transfers",
    "/admin/audit-logs",
)


@pytest.mark.parametrize("path", ADMIN_LIST_ROUTES)
def test_anonymous_admin_routes_are_blocked(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Cache-Control"] == "no-store, private"


@pytest.mark.parametrize("path", ADMIN_LIST_ROUTES)
def test_regular_user_admin_routes_are_403_and_no_store(
    client, user_factory, login_client, path
):
    user_factory("alice")
    login(client, login_client, "alice")
    response = client.get(path)
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store, private"


def test_dormant_admin_is_blocked(client, user_factory, login_client):
    user_factory("sleeping_admin", role="admin", status="dormant")
    response = login_client(client, username="sleeping_admin", password=PASSWORD)
    assert response.status_code == 401
    assert client.get("/admin").status_code == 302


def test_active_admin_routes_and_navigation_are_available(
    client, user_factory, login_client
):
    admin_login(client, user_factory, login_client)
    for path in ADMIN_LIST_ROUTES:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store, private"
    assert 'href="/admin"' in client.get("/").get_data(as_text=True)


def test_regular_navigation_hides_admin_link_but_server_still_denies(
    client, user_factory, login_client
):
    user_factory("alice")
    login(client, login_client, "alice")
    assert 'href="/admin"' not in client.get("/").get_data(as_text=True)
    assert client.get("/admin").status_code == 403


def test_admin_mutation_requires_csrf_and_current_password(
    client, user_factory, login_client
):
    admin_login(client, user_factory, login_client)
    user_factory("target")
    path = "/admin/users/target/status"
    assert (
        client.post(
            path, data={"status": "dormant", "current_password": PASSWORD}
        ).status_code
        == 400
    )
    token = csrf_from(client, "/admin/users/target")
    response = client.post(
        path,
        data={
            "csrf_token": token,
            "status": "dormant",
            "current_password": "incorrect-password",
        },
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "관리자 재인증 실패" in html
    assert "incorrect-password" not in html
    with client.application.app_context():
        assert (
            db.session.execute(
                db.select(User.status).where(User.username == "target")
            ).scalar_one()
            == "active"
        )


def test_admin_user_status_increments_version_audits_and_disconnects(
    app, client, user_factory, login_client, monkeypatch
):
    admin = admin_login(client, user_factory, login_client)
    target = user_factory("target")
    with app.app_context():
        before = db.session.get(User, target.id).auth_version
        registry = app.extensions["chat_connection_registry"]
        registry.add(
            sid="synthetic-sid",
            user_id=target.id,
            auth_version=before,
            max_connections=5,
        )
    disconnected = []
    monkeypatch.setattr(
        socketio.server,
        "disconnect",
        lambda sid, namespace: disconnected.append((sid, namespace)),
    )
    token = csrf_from(client, "/admin/users/target")
    response = client.post(
        "/admin/users/target/status",
        data={
            "csrf_token": token,
            "status": "dormant",
            "role": "admin",
            "target_id": admin.id,
            "current_password": PASSWORD,
        },
    )
    assert response.status_code == 303
    with app.app_context():
        stored = db.session.get(User, target.id)
        assert stored.role == "user"
        assert stored.status == "dormant"
        assert stored.auth_version == before + 1
        audit = db.session.execute(
            db.select(AuditLog).where(AuditLog.action == "admin.user.dormant")
        ).scalar_one()
        assert audit.actor_user_id == admin.id
        assert audit.target_id == target.id
        assert audit.details == {
            "previous_status": "active",
            "new_status": "dormant",
        }
        assert registry.user_connection_count(target.id) == 0
    assert disconnected == [("synthetic-sid", "/chat")]


def test_user_status_idempotent_does_not_increment_or_disconnect(app, user_factory):
    admin = user_factory("admin_user", role="admin")
    target = user_factory("target")
    with app.app_context():
        result = change_user_status(
            actor_id=admin.id,
            target_username=target.username,
            new_status="active",
        )
        stored = db.session.get(User, target.id)
        assert result is AdminMutationResult.IDEMPOTENT
        assert stored.auth_version == 1


def test_admin_cannot_dormant_self_or_last_active_admin(app, user_factory):
    first = user_factory("admin_one", role="admin")
    second = user_factory("admin_two", role="admin")
    with app.app_context():
        assert (
            change_user_status(
                actor_id=first.id,
                target_username=first.username,
                new_status="dormant",
            )
            is AdminMutationResult.SELF_PROTECTED
        )
        db.session.get(User, second.id).status = "dormant"
        db.session.commit()
        assert (
            change_user_status(
                actor_id=first.id,
                target_username=second.username,
                new_status="active",
            )
            is AdminMutationResult.OK
        )
        assert (
            change_user_status(
                actor_id=first.id,
                target_username=second.username,
                new_status="dormant",
            )
            is AdminMutationResult.OK
        )
        assert db.session.get(User, first.id).status == "active"


def test_other_admin_can_be_dormanted_when_one_active_admin_remains(app, user_factory):
    actor = user_factory("admin_one", role="admin")
    target = user_factory("admin_two", role="admin")
    with app.app_context():
        assert (
            change_user_status(
                actor_id=actor.id,
                target_username=target.username,
                new_status="dormant",
            )
            is AdminMutationResult.OK
        )
        assert db.session.get(User, target.id).status == "dormant"


def test_old_http_cookie_and_csrf_stay_invalid_after_restore(
    app, user_factory, login_client
):
    actor = user_factory("administrator", role="admin")
    target = user_factory("target")
    actor_http = app.test_client()
    target_http = app.test_client()
    login(actor_http, login_client, actor.username)
    login(target_http, login_client, target.username)
    old_csrf = csrf_from(target_http, "/me")
    dormant_token = csrf_from(actor_http, "/admin/users/target")
    assert (
        actor_http.post(
            "/admin/users/target/status",
            data={
                "csrf_token": dormant_token,
                "status": "dormant",
                "current_password": PASSWORD,
            },
        ).status_code
        == 303
    )
    restore_token = csrf_from(actor_http, "/admin/users/target")
    assert (
        actor_http.post(
            "/admin/users/target/status",
            data={
                "csrf_token": restore_token,
                "status": "active",
                "current_password": PASSWORD,
            },
        ).status_code
        == 303
    )
    assert target_http.get("/me").status_code == 302
    assert (
        target_http.post(
            "/me/bio",
            data={"csrf_token": old_csrf, "bio": "stale request"},
        ).status_code
        == 302
    )
    with app.app_context():
        assert db.session.get(User, target.id).bio == ""
    assert (
        login_client(target_http, username="target", password=PASSWORD).status_code
        == 303
    )
    assert target_http.get("/me").status_code == 200


@pytest.mark.parametrize(
    ("starting_status", "action", "expected", "previous"),
    [
        ("active", "hide", "hidden", "active"),
        ("sold", "hide", "hidden", "sold"),
        ("active", "delete", "deleted", None),
        ("sold", "delete", "deleted", None),
        ("hidden", "delete", "deleted", None),
    ],
)
def test_admin_product_status_transitions(
    app,
    user_factory,
    product_factory,
    starting_status,
    action,
    expected,
    previous,
):
    admin = user_factory("administrator", role="admin")
    product = product_factory(user_factory("seller"), status=starting_status)
    with app.app_context():
        if starting_status == "hidden":
            stored = db.session.get(Product, product.id)
            stored.moderation_previous_status = "active"
            db.session.commit()
        assert (
            change_product_status(
                actor_id=admin.id, product_id=product.id, action=action
            )
            is AdminMutationResult.OK
        )
        stored = db.session.get(Product, product.id)
        assert stored.status == expected
        assert stored.moderation_previous_status == previous
        assert stored.image_filename == product.image_filename


@pytest.mark.parametrize("previous", ["active", "sold", None])
def test_admin_product_restore_uses_previous_or_safe_active_fallback(
    app, user_factory, product_factory, previous
):
    admin = user_factory("administrator", role="admin")
    product = product_factory(user_factory("seller"), status="hidden")
    with app.app_context():
        stored = db.session.get(Product, product.id)
        stored.moderation_previous_status = previous
        db.session.commit()
        result = change_product_status(
            actor_id=admin.id, product_id=product.id, action="restore"
        )
        assert result is AdminMutationResult.OK
        assert stored.status == (previous or "active")
        assert stored.moderation_previous_status is None


def test_deleted_product_cannot_be_hidden_or_restored(
    app, user_factory, product_factory
):
    admin = user_factory("administrator", role="admin")
    product = product_factory(user_factory("seller"), status="deleted")
    with app.app_context():
        for action in ("hide", "restore"):
            assert (
                change_product_status(
                    actor_id=admin.id, product_id=product.id, action=action
                )
                is AdminMutationResult.INVALID_STATE
            )


def test_admin_product_route_ignores_seller_and_status_mass_assignment(
    app, client, csrf_token, user_factory, product_factory, login_client
):
    admin_login(client, user_factory, login_client)
    seller = user_factory("seller")
    attacker = user_factory("attacker")
    product = product_factory(seller)
    path = f"/admin/products/{product.id}"
    token = csrf_token(client, path)
    response = client.post(
        f"{path}/status",
        data={
            "csrf_token": token,
            "current_password": PASSWORD,
            "action": "hide",
            "seller_id": attacker.id,
            "status": "deleted",
        },
    )
    assert response.status_code == 303
    with app.app_context():
        stored = db.session.get(Product, product.id)
        assert stored.seller_id == seller.id
        assert stored.status == "hidden"


@pytest.mark.parametrize(
    ("decision", "expected", "audit_action"),
    [
        ("confirm", "confirmed", "admin.report.confirmed"),
        ("reject", "rejected", "admin.report.rejected"),
    ],
)
def test_admin_report_decision_sets_reviewer_and_audit(
    app, user_factory, decision, expected, audit_action
):
    admin = user_factory("administrator", role="admin")
    reporter = user_factory("reporter")
    target = user_factory("target")
    with app.app_context():
        report = Report(
            reporter_id=reporter.id,
            target_type="user",
            target_id=target.id,
            reason="관리자가 검토할 충분한 신고 사유",
        )
        db.session.add(report)
        db.session.commit()
        report_id = report.id
        assert (
            decide_report(actor_id=admin.id, report_id=report_id, decision=decision)
            is AdminMutationResult.OK
        )
        stored = db.session.get(Report, report_id)
        assert stored.status == expected
        assert stored.reviewed_by_id == admin.id
        assert stored.reviewed_at is not None
        audit = db.session.execute(
            db.select(AuditLog).where(AuditLog.action == audit_action)
        ).scalar_one()
        assert "reason" not in audit.details
        assert audit.details["target_type"] == "user"
        assert (
            decide_report(
                actor_id=admin.id,
                report_id=report_id,
                decision="reject" if decision == "confirm" else "confirm",
            )
            is AdminMutationResult.IDEMPOTENT
        )
        assert db.session.get(Report, report_id).status == expected


def test_message_hide_and_show_changes_future_history(
    app, client, user_factory, login_client
):
    admin = user_factory("administrator", role="admin")
    sender = user_factory("sender")
    with app.app_context():
        message = ChatMessage(sender_id=sender.id, body="visible body")
        db.session.add(message)
        db.session.commit()
        message_id = message.id
        assert (
            change_message_visibility(
                actor_id=admin.id, message_id=message_id, action="hide"
            )
            is AdminMutationResult.OK
        )
    sender_client = app.test_client()
    login(sender_client, login_client, sender.username)
    assert b"visible body" not in sender_client.get("/chat").data
    with app.app_context():
        assert (
            change_message_visibility(
                actor_id=admin.id, message_id=message_id, action="show"
            )
            is AdminMutationResult.OK
        )
    assert b"visible body" in sender_client.get("/chat").data


def test_admin_message_view_escapes_body_and_hides_internal_ids(
    app, client, user_factory, login_client
):
    sender = user_factory("sender")
    admin_login(client, user_factory, login_client)
    with app.app_context():
        message = ChatMessage(sender_id=sender.id, body="<script>alert(1)</script>")
        db.session.add(message)
        db.session.commit()
    html = client.get("/admin/messages").get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert sender.id not in html


def test_admin_transfer_list_is_read_only_and_redacted(
    app, client, user_factory, login_client
):
    sender = user_factory("sender")
    recipient = user_factory("recipient")
    admin_login(client, user_factory, login_client)
    with app.app_context():
        transfer = Transfer(
            sender_id=sender.id,
            recipient_id=recipient.id,
            amount=4321,
            idempotency_key="a" * 64,
        )
        db.session.add(transfer)
        db.session.commit()
        transfer_id = transfer.id
    response = client.get("/admin/transfers?q=sender&sort=oldest")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert transfer_id in html
    assert "sender" in html and "recipient" in html and "4321" in html
    assert "a" * 64 not in html
    assert sender.id not in html and recipient.id not in html


def test_transfer_url_map_has_only_user_create_and_read_only_admin(app):
    rules = tuple(app.url_map.iter_rules())
    admin_transfer_rules = [rule for rule in rules if rule.rule == "/admin/transfers"]
    assert len(admin_transfer_rules) == 1
    assert admin_transfer_rules[0].methods == {"GET", "HEAD", "OPTIONS"}
    transfer_posts = [
        rule
        for rule in rules
        if "transfer" in rule.rule.lower() and "POST" in rule.methods
    ]
    assert [(rule.rule, rule.endpoint) for rule in transfer_posts] == [
        ("/wallet/transfer", "wallet.transfer_submit")
    ]
    mutation_methods = {"POST", "PUT", "PATCH", "DELETE"}
    assert not [
        rule
        for rule in rules
        if {"PUT", "PATCH", "DELETE"}.intersection(rule.methods)
        and any(name in rule.rule.lower() for name in ("transfer", "wallet"))
    ]
    assert not [
        rule
        for rule in rules
        if mutation_methods.intersection(rule.methods)
        and rule.rule.startswith("/admin/transfers")
    ]


def test_admin_audit_list_shows_system_and_escapes_safe_details(
    app, client, user_factory, login_client
):
    admin_login(client, user_factory, login_client)
    with app.app_context():
        add_audit_log(
            actor_user_id=None,
            action="admin.account_created",
            target_type="user",
            target_id=None,
            details={"username": "<script>system</script>"},
        )
        db.session.commit()
    html = client.get("/admin/audit-logs").get_data(as_text=True)
    assert "system" in html
    assert "&lt;script&gt;system&lt;/script&gt;" in html
    assert "<script>system</script>" not in html
    assert client.post("/admin/audit-logs").status_code == 405


def test_admin_views_use_projection_dtos(
    app, client, user_factory, login_client, monkeypatch
):
    admin_login(client, user_factory, login_client)
    captured = []
    original = routes.render_template

    def capture(template, **context):
        captured.append(context)
        return original(template, **context)

    monkeypatch.setattr(routes, "render_template", capture)
    paths_and_types = (
        ("/admin/users", AdminUserPage),
        ("/admin/products", AdminProductPage),
        ("/admin/reports", AdminReportPage),
        ("/admin/messages", AdminMessagePage),
        ("/admin/transfers", AdminTransferPage),
        ("/admin/audit-logs", AdminAuditLogPage),
    )
    for path, expected_type in paths_and_types:
        assert client.get(path).status_code == 200
        assert isinstance(captured[-1]["page"], expected_type)
        assert captured[-1]["page"].per_page == 50
        assert not any(
            isinstance(value, (User, Product, Report, ChatMessage, Transfer, AuditLog))
            for value in captured[-1].values()
        )


@pytest.mark.parametrize(
    (
        "service_name",
        "page_type",
        "path",
        "request_filters",
        "expected_filters",
    ),
    [
        (
            "list_users",
            AdminUserPage,
            "/admin/users",
            {
                "q": '  alice & "<관리자>  ',
                "role": "user",
                "status": "dormant",
                "sort": "oldest",
            },
            {
                "q": 'alice & "<관리자>',
                "role": "user",
                "status": "dormant",
                "sort": "oldest",
            },
        ),
        (
            "list_products",
            AdminProductPage,
            "/admin/products",
            {"q": "needle", "status": "hidden", "sort": "oldest"},
            {"q": "needle", "status": "hidden", "sort": "oldest"},
        ),
        (
            "list_reports",
            AdminReportPage,
            "/admin/reports",
            {
                "q": "reporter",
                "target_type": "product",
                "status": "pending",
                "sort": "oldest",
            },
            {
                "q": "reporter",
                "target_type": "product",
                "status": "pending",
                "sort": "oldest",
            },
        ),
        (
            "list_messages",
            AdminMessagePage,
            "/admin/messages",
            {
                "q": "message",
                "scope": "direct",
                "visibility": "hidden",
                "sort": "oldest",
            },
            {
                "q": "message",
                "scope": "direct",
                "visibility": "hidden",
                "sort": "oldest",
            },
        ),
        (
            "list_transfers",
            AdminTransferPage,
            "/admin/transfers",
            {"q": "sender", "sort": "oldest"},
            {"q": "sender", "sort": "oldest"},
        ),
        (
            "list_audit_logs",
            AdminAuditLogPage,
            "/admin/audit-logs",
            {"q": "admin", "target_type": "report", "sort": "oldest"},
            {"q": "admin", "target_type": "report", "sort": "oldest"},
        ),
    ],
)
def test_admin_pagination_preserves_only_normalized_allowlisted_filters(
    client,
    user_factory,
    login_client,
    monkeypatch,
    service_name,
    page_type,
    path,
    request_filters,
    expected_filters,
):
    admin_login(client, user_factory, login_client)
    service_arguments = {}

    def page_service(**kwargs):
        service_arguments.update(kwargs)
        return page_type((), 2, 50, 101, 3)

    monkeypatch.setattr(routes, service_name, page_service)
    response = client.get(
        path,
        query_string={
            **request_filters,
            "page": "2",
            "per_page": "1",
            "unknown": "untrusted",
            "next": "https://attacker.example/",
            "redirect": "https://attacker.example/",
            "endpoint": "attacker.external",
        },
    )
    assert response.status_code == 200
    assert service_arguments["page"] == 2
    assert service_arguments["per_page"] == 50

    raw_hrefs = re.findall(r'href="([^"]+)"', response.get_data(as_text=True))
    pagination_hrefs = []
    for raw_href in raw_hrefs:
        parsed = urlsplit(unescape(raw_href))
        query = parse_qs(parsed.query)
        if parsed.path == path and "page" in query:
            pagination_hrefs.append((raw_href, parsed, query))

    assert len(pagination_hrefs) == 2
    assert {query["page"][0] for _, _, query in pagination_hrefs} == {"1", "3"}
    for raw_href, parsed, query in pagination_hrefs:
        assert parsed.scheme == ""
        assert parsed.netloc == ""
        assert parsed.path == path
        assert query == {
            **{name: [value] for name, value in expected_filters.items()},
            "page": [query["page"][0]],
        }
        assert "&amp;" in raw_href
        assert "per_page" not in raw_href
        assert "unknown" not in raw_href
        assert "attacker.example" not in raw_href

    if path == "/admin/users":
        for raw_href, _, _ in pagination_hrefs:
            assert "%26" in raw_href
            assert "%22" in raw_href
            assert "%3C" in raw_href
            assert "%3E" in raw_href


@pytest.mark.parametrize(
    "path",
    [
        "/admin/users/target/status",
        f"/admin/products/{uuid4()}/status",
        f"/admin/reports/{uuid4()}/decision",
        f"/admin/messages/{uuid4()}/visibility",
    ],
)
def test_admin_mutations_have_no_get_route(client, path):
    assert client.get(path).status_code == 405


def test_admin_state_and_audit_are_atomic_on_commit_failure(
    app, user_factory, monkeypatch
):
    admin = user_factory("administrator", role="admin")
    target = user_factory("target")
    with app.app_context():
        monkeypatch.setattr(
            db.session,
            "commit",
            lambda: (_ for _ in ()).throw(SQLAlchemyError("private sql")),
        )
        assert (
            change_user_status(
                actor_id=admin.id,
                target_username=target.username,
                new_status="dormant",
            )
            is AdminMutationResult.DATABASE_ERROR
        )
        assert db.session.get(User, target.id).status == "active"
        assert (
            db.session.execute(
                db.select(AuditLog).where(AuditLog.action == "admin.user.dormant")
            ).all()
            == []
        )


def test_database_constraints_for_phase05_metadata(app, user_factory):
    reviewer = user_factory("reviewer", role="admin")
    reporter = user_factory("reporter")
    target = user_factory("target")
    with app.app_context():
        for previous in ("invalid", ""):
            db.session.add(
                Product(
                    seller_id=reporter.id,
                    title="상품",
                    description="설명",
                    price=1,
                    moderation_previous_status=previous,
                )
            )
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()
        inconsistent = Report(
            reporter_id=reporter.id,
            target_type="user",
            target_id=target.id,
            reason="검토 일관성을 확인하는 충분한 사유",
            status="confirmed",
        )
        db.session.add(inconsistent)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        pending_with_reviewer = Report(
            reporter_id=reporter.id,
            target_type="product",
            target_id=str(uuid4()),
            reason="대기 상태 일관성을 확인하는 충분한 사유",
            reviewed_by_id=reviewer.id,
            reviewed_at=reviewer.created_at,
        )
        db.session.add(pending_with_reviewer)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        for action, target_type in (("", "user"), ("valid", "")):
            db.session.add(
                AuditLog(
                    action=action,
                    target_type=target_type,
                )
            )
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


def test_admin_list_filters_treat_sql_injection_as_literal(
    client, user_factory, login_client
):
    admin_login(client, user_factory, login_client)
    response = client.get("/admin/users?q=%27%20OR%201%3D1--")
    assert response.status_code == 200
    assert "administrator" not in response.get_data(as_text=True)


def test_no_web_route_changes_role(app, client, user_factory, login_client):
    admin_login(client, user_factory, login_client)
    target = user_factory("target")
    token = csrf_from(client, "/admin/users/target")
    client.post(
        "/admin/users/target/status",
        data={
            "csrf_token": token,
            "status": "active",
            "role": "admin",
            "current_password": PASSWORD,
        },
    )
    with app.app_context():
        assert db.session.get(User, target.id).role == "user"


def test_sensitive_values_are_absent_from_audit_details(app, user_factory):
    user_factory("administrator", role="admin")
    with app.app_context():
        forbidden = {
            "password",
            "password_hash",
            "secret",
            "csrf",
            "session",
            "cookie",
            "auth_version",
            "idempotency",
            "sid",
            "reason",
            "token",
        }
        for details in db.session.execute(db.select(AuditLog.details)).scalars():
            assert forbidden.isdisjoint({key.lower() for key in (details or {})})


def test_wallet_is_not_shown_on_admin_user_pages(
    app, client, user_factory, login_client
):
    admin_login(client, user_factory, login_client)
    target = user_factory("wealthy", balance=987654321)
    with app.app_context():
        assert db.session.get(Wallet, target.id).balance == 987654321
    assert "987654321" not in client.get("/admin/users").get_data(as_text=True)
    assert "987654321" not in client.get("/admin/users/wealthy").get_data(as_text=True)


def test_admin_detail_routes_filters_and_mutation_routes(
    app, client, user_factory, product_factory, login_client
):
    admin_login(client, user_factory, login_client)
    reporter = user_factory("reporter")
    target = user_factory("target")
    seller = user_factory("seller")
    product = product_factory(seller, title="needle product")
    with app.app_context():
        report = Report(
            reporter_id=reporter.id,
            target_type="product",
            target_id=product.id,
            reason="관리자 route 검증을 위한 충분한 신고 사유",
        )
        conversation = DirectConversation(
            user1_id=min(reporter.id, target.id),
            user2_id=max(reporter.id, target.id),
        )
        db.session.add_all((report, conversation))
        db.session.flush()
        message = ChatMessage(
            sender_id=reporter.id,
            conversation_id=conversation.id,
            body="needle message",
        )
        db.session.add(message)
        db.session.commit()
        report_id = report.id
        message_id = message.id

    for path in (
        "/admin/users/target",
        f"/admin/products/{product.id}",
        f"/admin/reports/{report_id}",
        "/admin/users?q=target&role=user&status=active&sort=oldest",
        "/admin/products?q=needle&status=active&sort=oldest",
        "/admin/reports?q=reporter&target_type=product&status=pending&sort=oldest",
        "/admin/messages?q=needle&scope=direct&visibility=visible&sort=oldest",
        "/admin/transfers?q=missing&sort=oldest",
        "/admin/audit-logs?q=missing&target_type=report&sort=oldest",
    ):
        assert client.get(path).status_code == 200

    report_token = csrf_from(client, f"/admin/reports/{report_id}")
    assert (
        client.post(
            f"/admin/reports/{report_id}/decision",
            data={
                "csrf_token": report_token,
                "decision": "confirm",
                "current_password": PASSWORD,
            },
        ).status_code
        == 303
    )
    message_token = csrf_from(client, "/admin/messages")
    assert (
        client.post(
            f"/admin/messages/{message_id}/visibility",
            data={
                "csrf_token": message_token,
                "action": "hide",
                "current_password": PASSWORD,
            },
        ).status_code
        == 303
    )
    with app.app_context():
        assert db.session.get(Report, report_id).status == "confirmed"
        assert db.session.get(ChatMessage, message_id).is_hidden is True


@pytest.mark.parametrize(
    "path",
    [
        "/admin/users/missing",
        f"/admin/products/{uuid4()}",
        f"/admin/reports/{uuid4()}",
    ],
)
def test_admin_missing_detail_is_404(client, user_factory, login_client, path):
    admin_login(client, user_factory, login_client)
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/admin/users?page=0",
        "/admin/products?sort=invalid",
        "/admin/reports?status=invalid",
        "/admin/messages?scope=invalid",
        "/admin/transfers?page=1001",
        "/admin/audit-logs?target_type=invalid",
    ],
)
def test_admin_filter_allowlists_reject_invalid_values(
    client, user_factory, login_client, path
):
    admin_login(client, user_factory, login_client)
    assert client.get(path).status_code == 400


def test_admin_service_invalid_and_missing_targets(app, user_factory):
    admin = user_factory("administrator", role="admin")
    with app.app_context():
        assert (
            change_user_status(
                actor_id=admin.id,
                target_username="missing",
                new_status="dormant",
            )
            is AdminMutationResult.NOT_FOUND
        )
        assert (
            change_user_status(
                actor_id=admin.id,
                target_username=admin.username,
                new_status="invalid",
            )
            is AdminMutationResult.INVALID_STATE
        )
        assert (
            change_product_status(
                actor_id=admin.id,
                product_id=str(uuid4()),
                action="hide",
            )
            is AdminMutationResult.NOT_FOUND
        )
        assert (
            change_product_status(
                actor_id=admin.id,
                product_id=str(uuid4()),
                action="invalid",
            )
            is AdminMutationResult.INVALID_STATE
        )
        assert (
            decide_report(
                actor_id=admin.id,
                report_id=str(uuid4()),
                decision="confirm",
            )
            is AdminMutationResult.NOT_FOUND
        )
        assert (
            decide_report(
                actor_id=admin.id,
                report_id=str(uuid4()),
                decision="invalid",
            )
            is AdminMutationResult.INVALID_STATE
        )
        assert (
            change_message_visibility(
                actor_id=admin.id,
                message_id=str(uuid4()),
                action="hide",
            )
            is AdminMutationResult.NOT_FOUND
        )
        assert (
            change_message_visibility(
                actor_id=admin.id,
                message_id=str(uuid4()),
                action="invalid",
            )
            is AdminMutationResult.INVALID_STATE
        )


@pytest.mark.parametrize(
    ("action", "details"),
    [
        ("unknown.action", {}),
        ("admin.account_created", {"reason": "sensitive"}),
        ("admin.account_created", {"username": ["not", "scalar"]}),
    ],
)
def test_audit_policy_rejects_unknown_sensitive_or_nonscalar_details(action, details):
    with pytest.raises(ValueError):
        validate_audit_details(action, details)


def test_audit_display_drops_untrusted_or_non_mapping_details():
    assert safe_details_for_display("unknown.action", {"x": "y"}) == ()
    assert safe_details_for_display("admin.account_created", ["not", "dict"]) == ()
    assert validate_audit_details("admin.account_created", None) is None

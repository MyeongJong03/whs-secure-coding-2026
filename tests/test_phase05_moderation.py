import re

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db, limiter, socketio
from app.models import AuditLog, Product, Report, User
from app.moderation import routes
from app.moderation.policy import ReportReasonError, normalize_report_reason
from app.moderation.services import (
    ReportCreateResult,
    create_product_report,
    create_user_report,
)
from app.moderation.views import OwnReportPage


PASSWORD = "valid-test-password-123"


def login(client, login_client, username="alice"):
    assert login_client(client, username=username, password=PASSWORD).status_code == 303


def post_csrf(client, path, data):
    response = client.get(path)
    assert response.status_code == 200
    token = (
        re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
        .group(1)
        .decode()
    )
    return client.post(path, data={"csrf_token": token, **data})


@pytest.mark.parametrize(
    "value",
    [
        None,
        123,
        "short",
        "a" * 501,
        "valid reason\x00",
        "valid reason\x01",
        "valid reason\x7f",
    ],
)
def test_report_reason_rejects_invalid_values(app, value):
    with app.app_context(), pytest.raises(ReportReasonError):
        normalize_report_reason(value)


def test_report_reason_normalizes_crlf_carriage_return_nfc_and_whitespace(app):
    with app.app_context():
        assert normalize_report_reason("  e\u0301 reason\r\nline\rnext  ") == (
            "é reason\nline\nnext"
        )


def test_report_reason_rejects_utf8_byte_overflow(app):
    with app.app_context():
        app.config["REPORT_REASON_MAX_CHARS"] = 1000
        with pytest.raises(ReportReasonError):
            normalize_report_reason("😀" * 501)


def test_user_report_route_uses_server_identity_and_escapes_reason(
    app, client, csrf_token, user_factory, login_client
):
    reporter = user_factory("alice")
    target = user_factory("bobby")
    login(client, login_client)
    token = csrf_token(client, "/reports/users/bobby/new")
    response = client.post(
        "/reports/users/bobby/new",
        data={
            "csrf_token": token,
            "reason": "<script>alert(1)</script> 충분한 신고 사유",
            "reporter_id": target.id,
            "target_id": reporter.id,
            "target_type": "product",
            "status": "confirmed",
        },
    )
    assert response.status_code == 303
    with app.app_context():
        report = db.session.execute(db.select(Report)).scalar_one()
        assert report.reporter_id == reporter.id
        assert report.target_id == target.id
        assert report.target_type == "user"
        assert report.status == "pending"
        assert report.reviewed_by_id is None
        audit = db.session.execute(
            db.select(AuditLog).where(AuditLog.action == "report.created")
        ).scalar_one()
        assert "reason" not in (audit.details or {})
    html = client.get("/me/reports").get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert target.id not in html


def test_product_report_and_duplicate_are_handled(
    app, client, csrf_token, user_factory, product_factory, login_client
):
    user_factory("alice")
    seller = user_factory("seller")
    product = product_factory(seller)
    login(client, login_client)
    path = f"/reports/products/{product.id}/new"
    token = csrf_token(client, path)
    first = client.post(
        path, data={"csrf_token": token, "reason": "상품 신고 사유가 충분히 깁니다"}
    )
    second = client.post(
        path,
        data={"csrf_token": token, "reason": "다시 작성한 충분한 신고 사유"},
        follow_redirects=True,
    )
    assert first.status_code == 303
    assert second.status_code == 200
    assert "이미 신고한 대상" in second.get_data(as_text=True)
    with app.app_context():
        assert db.session.execute(db.select(Report)).scalars().all().__len__() == 1


def test_self_and_unavailable_report_targets_are_not_accepted(
    app, client, csrf_token, user_factory, product_factory, login_client
):
    alice = user_factory("alice")
    own_product = product_factory(alice)
    dormant = user_factory("sleepy", status="dormant")
    hidden = product_factory(
        user_factory("seller"), status="hidden", image_filename="1" * 32 + ".png"
    )
    login(client, login_client)
    assert client.get("/reports/users/alice/new").status_code == 404
    assert client.get(f"/reports/products/{own_product.id}/new").status_code == 404
    assert client.get(f"/reports/users/{dormant.username}/new").status_code == 404
    assert client.get(f"/reports/products/{hidden.id}/new").status_code == 404
    with app.app_context():
        assert db.session.execute(db.select(Report.id)).all() == []


@pytest.mark.parametrize("starting_status", ["active", "sold"])
def test_third_distinct_report_auto_hides_product_and_preserves_status(
    app, user_factory, product_factory, starting_status
):
    reporters = [user_factory(f"reporter{i}") for i in range(3)]
    product = product_factory(
        user_factory("seller"),
        status=starting_status,
        image_filename="2" * 32 + ".png",
    )
    with app.app_context():
        results = [
            create_product_report(
                reporter_id=reporter.id,
                product_id=product.id,
                reason="상품을 신고할 충분하고 구체적인 사유",
            )
            for reporter in reporters
        ]
        stored = db.session.get(Product, product.id)
        assert results == [
            ReportCreateResult.CREATED,
            ReportCreateResult.CREATED,
            ReportCreateResult.AUTO_RESTRICTED,
        ]
        assert stored.status == "hidden"
        assert stored.moderation_previous_status == starting_status
        automatic = db.session.execute(
            db.select(AuditLog).where(
                AuditLog.action == "moderation.product.auto_hidden"
            )
        ).scalar_one()
        assert automatic.actor_user_id is None
        assert automatic.details["report_count"] == 3


def test_rejected_report_does_not_count_toward_future_threshold(
    app, user_factory, product_factory
):
    reporters = [user_factory(f"reporter{i}") for i in range(4)]
    product = product_factory(user_factory("seller"))
    reviewer = user_factory("reviewer", role="admin")
    with app.app_context():
        assert (
            create_product_report(
                reporter_id=reporters[0].id,
                product_id=product.id,
                reason="첫 번째 신고 사유가 충분히 깁니다",
            )
            is ReportCreateResult.CREATED
        )
        first = db.session.execute(db.select(Report)).scalar_one()
        first.status = "rejected"
        first.reviewed_by_id = reviewer.id
        first.reviewed_at = first.created_at
        db.session.commit()
        for reporter in reporters[1:3]:
            assert (
                create_product_report(
                    reporter_id=reporter.id,
                    product_id=product.id,
                    reason="추가 신고 사유가 충분히 깁니다",
                )
                is ReportCreateResult.CREATED
            )
        assert db.session.get(Product, product.id).status == "active"
        assert (
            create_product_report(
                reporter_id=reporters[3].id,
                product_id=product.id,
                reason="마지막 신고 사유가 충분히 깁니다",
            )
            is ReportCreateResult.AUTO_RESTRICTED
        )


def test_third_report_auto_dormants_user_increments_version_and_disconnects(
    app, user_factory
):
    reporters = [user_factory(f"reporter{i}") for i in range(3)]
    target = user_factory("target")
    with app.app_context():
        before = db.session.get(User, target.id).auth_version
        results = [
            create_user_report(
                reporter_id=reporter.id,
                target_username="target",
                reason="사용자를 신고할 충분하고 구체적인 사유",
            )
            for reporter in reporters
        ]
        stored = db.session.get(User, target.id)
        assert results[-1] is ReportCreateResult.AUTO_RESTRICTED
        assert stored.status == "dormant"
        assert stored.auth_version == before + 1


def test_admin_reports_are_stored_without_automatic_dormancy(app, user_factory):
    reporters = [user_factory(f"reporter{i}") for i in range(3)]
    target = user_factory("admin_target", role="admin")
    with app.app_context():
        for reporter in reporters:
            assert (
                create_user_report(
                    reporter_id=reporter.id,
                    target_username=target.username,
                    reason="관리자 신고는 수동 검토가 필요한 사유입니다",
                )
                is ReportCreateResult.CREATED
            )
        stored = db.session.get(User, target.id)
        assert stored.status == "active"
        assert stored.auth_version == 1
        assert (
            db.session.execute(db.select(Report).where(Report.status == "pending"))
            .scalars()
            .all()
            .__len__()
            == 3
        )


def test_audit_failure_rolls_back_report_and_target_change(
    app, user_factory, product_factory, monkeypatch
):
    reporters = [user_factory(f"reporter{i}") for i in range(3)]
    product = product_factory(user_factory("seller"))
    with app.app_context():
        for reporter in reporters[:2]:
            create_product_report(
                reporter_id=reporter.id,
                product_id=product.id,
                reason="정상적으로 접수되는 충분한 신고 사유",
            )
        original = __import__(
            "app.moderation.services", fromlist=["add_audit_log"]
        ).add_audit_log

        def fail_automatic_audit(**kwargs):
            if kwargs["action"] == "moderation.product.auto_hidden":
                raise SQLAlchemyError("private database failure")
            return original(**kwargs)

        monkeypatch.setattr(
            "app.moderation.services.add_audit_log", fail_automatic_audit
        )
        result = create_product_report(
            reporter_id=reporters[2].id,
            product_id=product.id,
            reason="실패를 검증하기 위한 충분한 신고 사유",
        )
        assert result is ReportCreateResult.DATABASE_ERROR
        assert db.session.get(Product, product.id).status == "active"
        assert (
            db.session.execute(db.select(Report).where(Report.target_id == product.id))
            .scalars()
            .all()
            .__len__()
            == 2
        )


def test_report_unique_constraint_blocks_duplicate_race(app, user_factory):
    reporter = user_factory("alice")
    target = user_factory("bobby")
    with app.app_context():
        db.session.add_all(
            [
                Report(
                    reporter_id=reporter.id,
                    target_type="user",
                    target_id=target.id,
                    reason="중복 신고를 막기 위한 충분한 사유",
                ),
                Report(
                    reporter_id=reporter.id,
                    target_type="user",
                    target_id=target.id,
                    reason="중복 신고를 막기 위한 다른 사유",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_shared_report_rate_limit_counts_both_endpoints(
    app, client, csrf_token, user_factory, product_factory, login_client
):
    user_factory("alice")
    user_factory("bobby")
    product = product_factory(user_factory("seller"))
    login(client, login_client)
    user_path = "/reports/users/bobby/new"
    product_path = f"/reports/products/{product.id}/new"
    user_token = csrf_token(client, user_path)
    product_token = csrf_token(client, product_path)
    for index in range(10):
        path, token = (
            (user_path, user_token) if index % 2 == 0 else (product_path, product_token)
        )
        response = client.post(path, data={"csrf_token": token, "reason": "short"})
        assert response.status_code == 400
    assert (
        client.post(
            user_path, data={"csrf_token": user_token, "reason": "short"}
        ).status_code
        == 429
    )
    limiter.reset()


def test_own_report_page_is_fixed_projection_and_no_store(
    app, client, user_factory, login_client, monkeypatch
):
    reporter = user_factory("alice")
    target = user_factory("bobby")
    with app.app_context():
        db.session.add(
            Report(
                reporter_id=reporter.id,
                target_type="user",
                target_id=target.id,
                reason="목록에 표시할 충분한 신고 사유",
            )
        )
        db.session.commit()
    login(client, login_client)
    captured = {}
    original = routes.render_template

    def capture(template, **context):
        captured.update(context)
        return original(template, **context)

    monkeypatch.setattr(routes, "render_template", capture)
    response = client.get("/me/reports")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"
    page = captured["page"]
    assert isinstance(page, OwnReportPage)
    assert page.per_page == 20
    assert not hasattr(page.items[0], "target_id")
    assert not hasattr(page.items[0], "auth_version")


def test_report_database_failure_is_generic_and_rolls_back(
    app, user_factory, monkeypatch
):
    reporter = user_factory("alice")
    target = user_factory("bobby")
    with app.app_context():
        monkeypatch.setattr(
            db.session,
            "commit",
            lambda: (_ for _ in ()).throw(SQLAlchemyError("secret constraint")),
        )
        result = create_user_report(
            reporter_id=reporter.id,
            target_username=target.username,
            reason="데이터베이스 실패를 검증하는 충분한 사유",
        )
        assert result is ReportCreateResult.DATABASE_ERROR
        assert db.session.execute(db.select(Report.id)).all() == []


def test_report_service_revalidates_reason(app, user_factory):
    reporter = user_factory("alice")
    target = user_factory("bobby")
    with app.app_context():
        assert (
            create_user_report(
                reporter_id=reporter.id,
                target_username=target.username,
                reason="short",
            )
            is ReportCreateResult.DATABASE_ERROR
        )
        assert db.session.execute(db.select(Report.id)).all() == []


def test_auto_dormancy_disconnects_connected_socket(
    app, user_factory, login_client, monkeypatch
):
    reporters = [user_factory(f"reporter{i}") for i in range(3)]
    target = user_factory("target")
    target_http = app.test_client()
    login(target_http, login_client, "target")
    registry = app.extensions["chat_connection_registry"]
    registry.add(
        sid="synthetic-sid",
        user_id=target.id,
        auth_version=1,
        max_connections=5,
    )
    disconnected = []
    monkeypatch.setattr(
        socketio.server,
        "disconnect",
        lambda sid, namespace: disconnected.append((sid, namespace)),
    )
    with app.app_context():
        for reporter in reporters:
            create_user_report(
                reporter_id=reporter.id,
                target_username="target",
                reason="소켓 종료를 검증하는 충분한 신고 사유",
            )
    assert registry.user_connection_count(target.id) == 0
    assert disconnected == [("synthetic-sid", "/chat")]
    assert target_http.get("/me").status_code == 302

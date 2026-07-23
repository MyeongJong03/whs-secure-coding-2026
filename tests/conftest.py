import re

import pytest

from app import create_app
from app.extensions import db, limiter
from app.models import User, Wallet


@pytest.fixture
def app():
    application = create_app("testing")
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

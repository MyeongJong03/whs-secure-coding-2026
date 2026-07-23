import secrets
from datetime import timedelta


KNOWN_UNSAFE_SECRET_KEYS = frozenset(
    {
        "replace-with-a-long-random-local-value",
        "secret" + "!",
    }
)


def validate_secret_key(value: object) -> str:
    if not isinstance(value, str):
        raise RuntimeError(
            "SECRET_KEY must be a random string of at least 32 characters"
        )

    normalized_value = value.strip()
    if len(normalized_value) < 32 or normalized_value in KNOWN_UNSAFE_SECRET_KEYS:
        raise RuntimeError(
            "SECRET_KEY must be a random string of at least 32 characters "
            "and must not use a known placeholder"
        )
    return normalized_value


class BaseConfig:
    SECRET_KEY = None
    SQLALCHEMY_DATABASE_URI = "sqlite:///market.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    PRODUCT_UPLOAD_DIR = None
    PRODUCT_MAX_FILE_BYTES = 4 * 1024 * 1024
    PRODUCT_MAX_DIMENSION = 4096
    PRODUCT_MAX_PIXELS = 16_000_000
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True
    CHAT_HISTORY_PER_PAGE = 50
    CHAT_CONVERSATIONS_PER_PAGE = 20
    CHAT_PAGE_MAX = 1000
    CHAT_MESSAGE_MAX_CHARS = 500
    CHAT_MESSAGE_MAX_BYTES = 2000
    CHAT_MESSAGE_BURST_LIMIT = 5
    CHAT_MESSAGE_BURST_WINDOW_SECONDS = 10
    CHAT_MESSAGE_HOURLY_LIMIT = 120
    CHAT_JOIN_LIMIT = 30
    CHAT_JOIN_WINDOW_SECONDS = 60
    CHAT_MAX_CONNECTIONS_PER_USER = 5
    CHAT_SOCKET_MAX_AGE_SECONDS = 1800
    CHAT_CLOCK = None
    DEBUG = False


class DevelopmentConfig(BaseConfig):
    pass


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = secrets.token_urlsafe(32)
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = True
    PROPAGATE_EXCEPTIONS = False


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

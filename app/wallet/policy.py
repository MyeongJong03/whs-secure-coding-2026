import hashlib
import re


IDEMPOTENCY_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def normalize_recipient_username(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not 4 <= len(normalized) <= 32:
        return None
    if USERNAME_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def valid_idempotency_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and IDEMPOTENCY_TOKEN_PATTERN.fullmatch(value) is not None
    )


def derive_idempotency_key(sender_user_id: str, raw_token: str) -> str:
    material = f"{sender_user_id}:{raw_token}".encode()
    return hashlib.sha256(material).hexdigest()

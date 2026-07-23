import unicodedata
import uuid
from dataclasses import dataclass

from flask import current_app


CHAT_NAMESPACE = "/chat"
GLOBAL_ROOM = "chat:global"
SOCKET_IO_INTEGRITY = (
    "sha384-kzavj5fiMwLKzzD1f8S7TeoVIEi7uKHvbTA3ueZkrzYq75pNQUiUi6Dy98Q3fxb0"
)
GENERIC_CODES = frozenset(
    {
        "invalid_payload",
        "unauthorized",
        "not_found",
        "unavailable",
        "not_joined",
        "rate_limited",
        "server_error",
    }
)


@dataclass(frozen=True, slots=True)
class MessageValidationResult:
    valid: bool
    body: str | None = None


def direct_room(conversation_id: str) -> str:
    return f"chat:direct:{conversation_id}"


def canonical_uuid(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
    canonical = str(parsed)
    return canonical if value == canonical else None


def normalize_message_body(value: object) -> MessageValidationResult:
    if not isinstance(value, str):
        return MessageValidationResult(valid=False)

    normalized = unicodedata.normalize(
        "NFC", value.replace("\r\n", "\n").replace("\r", "\n")
    )
    normalized = normalized.strip()
    max_chars = current_app.config["CHAT_MESSAGE_MAX_CHARS"]
    max_bytes = current_app.config["CHAT_MESSAGE_MAX_BYTES"]
    if not 1 <= len(normalized) <= max_chars:
        return MessageValidationResult(valid=False)
    encoded = normalized.encode("utf-8")
    if not 1 <= len(encoded) <= max_bytes:
        return MessageValidationResult(valid=False)
    for character in normalized:
        codepoint = ord(character)
        if codepoint == 0x7F or (codepoint < 0x20 and character not in {"\n", "\t"}):
            return MessageValidationResult(valid=False)
    return MessageValidationResult(valid=True, body=normalized)


def exact_payload(payload: object, keys: frozenset[str]) -> bool:
    return isinstance(payload, dict) and frozenset(payload) == keys


def ack_success() -> dict[str, bool]:
    return {"ok": True}


def ack_error(code: str) -> dict[str, bool | str]:
    safe_code = code if code in GENERIC_CODES else "server_error"
    return {"ok": False, "code": safe_code}

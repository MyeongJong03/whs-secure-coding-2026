from collections.abc import Mapping


ACTION_DETAIL_KEYS: dict[str, frozenset[str]] = {
    "report.created": frozenset({"target_type"}),
    "moderation.product.auto_hidden": frozenset(
        {"previous_status", "new_status", "report_count"}
    ),
    "moderation.user.auto_dormant": frozenset(
        {"previous_status", "new_status", "report_count"}
    ),
    "admin.account_created": frozenset({"username"}),
    "admin.user.dormant": frozenset({"previous_status", "new_status"}),
    "admin.user.active": frozenset({"previous_status", "new_status"}),
    "admin.product.hidden": frozenset({"previous_status", "new_status"}),
    "admin.product.restored": frozenset({"previous_status", "new_status"}),
    "admin.product.deleted": frozenset({"previous_status", "new_status"}),
    "admin.report.confirmed": frozenset(
        {"target_type", "decision", "previous_status", "new_status"}
    ),
    "admin.report.rejected": frozenset(
        {"target_type", "decision", "previous_status", "new_status"}
    ),
    "admin.message.hidden": frozenset(
        {"previous_visibility", "new_visibility", "scope"}
    ),
    "admin.message.visible": frozenset(
        {"previous_visibility", "new_visibility", "scope"}
    ),
}

FORBIDDEN_DETAIL_TERMS = frozenset(
    {
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
)
SCALAR_TYPES = (str, int, bool, type(None))


def validate_audit_details(
    action: str, details: Mapping[str, object] | None
) -> dict[str, str | int | bool | None] | None:
    allowed_keys = ACTION_DETAIL_KEYS.get(action)
    if allowed_keys is None:
        raise ValueError("Audit action is not allowlisted")
    if details is None:
        return None
    if set(details) - allowed_keys:
        raise ValueError("Audit details contain disallowed keys")

    safe: dict[str, str | int | bool | None] = {}
    for key, value in details.items():
        lowered = key.lower()
        if any(term in lowered for term in FORBIDDEN_DETAIL_TERMS):
            raise ValueError("Audit details contain a sensitive key")
        if not isinstance(value, SCALAR_TYPES):
            raise ValueError("Audit detail values must be scalar")
        safe[key] = value
    return safe


def safe_details_for_display(
    action: str, details: object
) -> tuple[tuple[str, str | int | bool | None], ...]:
    if not isinstance(details, dict):
        return ()
    try:
        safe = validate_audit_details(action, details)
    except ValueError:
        return ()
    return tuple(sorted((safe or {}).items()))

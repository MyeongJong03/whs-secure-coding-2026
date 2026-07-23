from collections.abc import Mapping

from app.audit.policy import validate_audit_details
from app.extensions import db
from app.models import AuditLog


def add_audit_log(
    *,
    actor_user_id: str | None,
    action: str,
    target_type: str,
    target_id: str | None,
    details: Mapping[str, object] | None = None,
) -> AuditLog:
    if not isinstance(target_type, str) or not 1 <= len(target_type) <= 50:
        raise ValueError("Audit target type is invalid")
    safe_details = validate_audit_details(action, details)
    audit_log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=safe_details,
    )
    db.session.add(audit_log)
    return audit_log

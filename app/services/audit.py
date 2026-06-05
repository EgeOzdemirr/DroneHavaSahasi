from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def write_audit_log(
    db: Session,
    *,
    actor_username: str,
    action: str,
    entity_type: str,
    entity_id: str | None,
    details: dict[str, Any] | None = None,
    success: bool = True,
) -> AuditLog:
    item = AuditLog(
        actor_username=actor_username,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
        success=success,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


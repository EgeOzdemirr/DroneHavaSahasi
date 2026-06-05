from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.schemas.models import AuditLogResponse

router = APIRouter(prefix="/v1/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    limit: int = 200,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> list[AuditLogResponse]:
    rows = db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).scalars().all()
    return [AuditLogResponse.model_validate(item) for item in rows]


from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_csrf_for_cookie_auth, require_roles
from app.db.models import Alert, User
from app.db.session import get_db
from app.domain.enums import AlertStatus, UserRole
from app.schemas.models import AlertAckResponse, AlertResponse
from app.services.audit import write_audit_log

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    status_filter: AlertStatus | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> list[AlertResponse]:
    stmt = select(Alert).order_by(Alert.created_at.desc())
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    rows = db.execute(stmt).scalars().all()
    return [AlertResponse.model_validate(item) for item in rows]


@router.post("/{alert_id}/ack", response_model=AlertAckResponse)
def ack_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> AlertAckResponse:
    item = db.execute(select(Alert).where(Alert.id == alert_id)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    item.status = AlertStatus.ack
    item.acked_at = datetime.now(timezone.utc)
    item.acked_by = current_user.id
    db.commit()

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="alert_ack",
        entity_type="alert",
        entity_id=item.id,
        details={},
    )
    return AlertAckResponse(id=item.id, status=item.status, acked_at=item.acked_at, acked_by=item.acked_by)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_csrf_for_cookie_auth, require_roles
from sqlalchemy import select

from app.db.models import OperatorStation, User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.schemas.models import HostileContactIngestRequest, HostileDetectionResponse
from app.services.audit import write_audit_log
from app.services.field_layer_effects import list_active_field_layers
from app.services.intercept_control import InterceptControlError, build_detection_response, ingest_recon_contact

router = APIRouter(prefix="/v1/recon", tags=["recon"])


@router.post("/contacts", response_model=HostileDetectionResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_contact(
    payload: HostileContactIngestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> HostileDetectionResponse:
    try:
        result = ingest_recon_contact(db, payload)
    except InterceptControlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="recon_contact_ingest",
        entity_type="hostile_detection",
        entity_id=result.detection.id,
        details={
            "recon_drone_uid": payload.recon_drone_uid,
            "contact_id": payload.contact_id,
            "assigned_task": None if result.task is None else result.task.id,
        },
    )
    station = None
    if result.detection.assigned_operator_station_id:
        station = db.execute(
            select(OperatorStation).where(OperatorStation.id == result.detection.assigned_operator_station_id)
        ).scalar_one_or_none()
    return build_detection_response(result.detection, station, field_layers=list_active_field_layers(db))

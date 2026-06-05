from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_csrf_for_cookie_auth, require_roles
from app.db.models import HostileDetection, InterceptTask, OperatorStation, User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.schemas.models import HostileDetectionResponse
from app.services.audit import write_audit_log
from app.services.field_layer_effects import list_active_field_layers
from app.services.intercept_control import build_detection_response, list_detection_rows
from app.services.intercept_simulation import advance_intercept_simulation

router = APIRouter(prefix="/v1/hostile-detections", tags=["hostile-detections"])


@router.get("", response_model=list[HostileDetectionResponse])
def list_hostile_detections(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> list[HostileDetectionResponse]:
    field_layers = list_active_field_layers(db)
    return [
        build_detection_response(detection, station, field_layers=field_layers)
        for detection, station in list_detection_rows(db)
    ]


@router.get("/{detection_id}", response_model=HostileDetectionResponse)
def get_hostile_detection(
    detection_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> HostileDetectionResponse:
    advance_intercept_simulation(db)
    row = db.execute(
        select(HostileDetection, OperatorStation)
        .join(OperatorStation, OperatorStation.id == HostileDetection.assigned_operator_station_id, isouter=True)
        .where(HostileDetection.id == detection_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hostile detection not found")
    detection, station = row
    return build_detection_response(detection, station, field_layers=list_active_field_layers(db))


@router.delete("/{detection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hostile_detection(
    detection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> None:
    detection = db.execute(select(HostileDetection).where(HostileDetection.id == detection_id)).scalar_one_or_none()
    if detection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hedef tespiti bulunamadı")

    tasks = db.execute(select(InterceptTask).where(InterceptTask.hostile_detection_id == detection.id)).scalars().all()
    contact_id = detection.contact_id
    task_ids = [item.id for item in tasks]
    for task in tasks:
        db.delete(task)
    db.flush()
    db.delete(detection)
    db.commit()

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="hostile_detection_delete",
        entity_type="hostile_detection",
        entity_id=detection_id,
        details={"contact_id": contact_id, "deleted_task_ids": task_ids},
    )
    return

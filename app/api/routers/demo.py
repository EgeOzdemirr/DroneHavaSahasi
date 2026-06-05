from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_csrf_for_cookie_auth, require_roles
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.schemas.models import (
    DemoDetectionCreateRequest,
    DemoDetectionCreateResponse,
    DemoResetResponse,
    DemoScenarioSeedRequest,
    DemoScenarioSeedResponse,
)
from app.services.audit import write_audit_log
from app.services.demo_control import DemoControlError, create_demo_detection, reset_demo_scenario, seed_demo_scenario

router = APIRouter(prefix="/v1/demo", tags=["demo"])
settings = get_settings()


def require_demo_mode() -> None:
    if not settings.demo_mode_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo modu kapalı")


@router.post("/scenario", response_model=DemoScenarioSeedResponse)
def seed_scenario(
    payload: DemoScenarioSeedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
    _demo_ok: None = Depends(require_demo_mode),
) -> DemoScenarioSeedResponse:
    try:
        result = seed_demo_scenario(db, payload)
    except DemoControlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="demo_scenario_seed",
        entity_type="demo",
        entity_id=result.recon_drone_uid,
        details={"station_count": len(result.operators)},
    )
    return result


@router.post("/detections", response_model=DemoDetectionCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_detection(
    payload: DemoDetectionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
    _demo_ok: None = Depends(require_demo_mode),
) -> DemoDetectionCreateResponse:
    try:
        result = create_demo_detection(db, payload)
    except DemoControlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="demo_detection_create",
        entity_type="hostile_detection",
        entity_id=result.detection.id,
        details={
            "contact_id": payload.contact_id,
            "assigned_task_id": result.assigned_task_id,
            "assigned_station_name": result.assigned_station_name,
        },
    )
    return result


@router.post("/reset", response_model=DemoResetResponse)
def reset_scenario(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
    _demo_ok: None = Depends(require_demo_mode),
) -> DemoResetResponse:
    result = reset_demo_scenario(db)
    write_audit_log(
        db,
        actor_username=current_user.username,
        action="demo_reset",
        entity_type="demo",
        entity_id="demo",
        details=result.model_dump(),
    )
    return result

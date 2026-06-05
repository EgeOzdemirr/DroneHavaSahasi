from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_csrf_for_cookie_auth, require_roles
from app.db.models import User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.schemas.models import InterceptTaskResponse, TaskActionRequest
from app.services.audit import write_audit_log
from app.services.field_layer_effects import list_active_field_layers
from app.services.intercept_control import (
    InterceptControlError,
    accept_task,
    build_task_response,
    complete_task,
    list_task_rows,
    reject_task,
)

router = APIRouter(prefix="/v1/intercept-tasks", tags=["intercept-tasks"])


def _operator_scope(current_user: User) -> str | None:
    if current_user.role == UserRole.operator:
        return current_user.id
    return None


@router.get("", response_model=list[InterceptTaskResponse])
def list_intercept_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> list[InterceptTaskResponse]:
    rows = list_task_rows(db, operator_user_id=_operator_scope(current_user))
    field_layers = list_active_field_layers(db)
    return [
        build_task_response(task, detection, station, user, drone, field_layers=field_layers)
        for task, detection, station, user, drone in rows
    ]


@router.get("/me", response_model=list[InterceptTaskResponse])
def list_my_intercept_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
) -> list[InterceptTaskResponse]:
    operator_id = current_user.id if current_user.role == UserRole.operator else None
    rows = list_task_rows(db, operator_user_id=operator_id)
    field_layers = list_active_field_layers(db)
    return [
        build_task_response(task, detection, station, user, drone, field_layers=field_layers)
        for task, detection, station, user, drone in rows
    ]


@router.post("/{task_id}/accept", response_model=InterceptTaskResponse)
def accept_intercept_task(
    task_id: str,
    payload: TaskActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> InterceptTaskResponse:
    try:
        task = accept_task(
            db,
            task_id=task_id,
            operator_user_id=_operator_scope(current_user),
            note=payload.operator_note,
        )
    except InterceptControlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="intercept_task_accept",
        entity_type="intercept_task",
        entity_id=task.id,
        details={"operator_note": payload.operator_note},
    )
    row = list_task_rows(db, operator_user_id=None)
    field_layers = list_active_field_layers(db)
    for item in row:
        if item[0].id == task.id:
            return build_task_response(*item, field_layers=field_layers)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angajman görevi kabul işleminden sonra bulunamadı")


@router.post("/{task_id}/reject", response_model=InterceptTaskResponse)
def reject_intercept_task(
    task_id: str,
    payload: TaskActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> InterceptTaskResponse:
    try:
        task = reject_task(
            db,
            task_id=task_id,
            operator_user_id=_operator_scope(current_user),
            note=payload.operator_note,
        )
    except InterceptControlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="intercept_task_reject",
        entity_type="intercept_task",
        entity_id=task.id,
        details={"operator_note": payload.operator_note},
    )
    row = list_task_rows(db, operator_user_id=None)
    field_layers = list_active_field_layers(db)
    for item in row:
        if item[0].id == task.id:
            return build_task_response(*item, field_layers=field_layers)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angajman görevi ret işleminden sonra bulunamadı")


@router.post("/{task_id}/complete", response_model=InterceptTaskResponse)
def complete_intercept_task(
    task_id: str,
    payload: TaskActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.operator)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> InterceptTaskResponse:
    try:
        task = complete_task(
            db,
            task_id=task_id,
            operator_user_id=_operator_scope(current_user),
            note=payload.operator_note,
        )
    except InterceptControlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="intercept_task_complete",
        entity_type="intercept_task",
        entity_id=task.id,
        details={"operator_note": payload.operator_note},
    )
    row = list_task_rows(db, operator_user_id=None)
    field_layers = list_active_field_layers(db)
    for item in row:
        if item[0].id == task.id:
            return build_task_response(*item, field_layers=field_layers)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angajman görevi tamamlama işleminden sonra bulunamadı")

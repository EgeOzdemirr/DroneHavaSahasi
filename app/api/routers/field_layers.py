from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_csrf_for_cookie_auth, require_roles
from app.db.models import FieldLayer, User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.schemas.models import FieldLayerCreateRequest, FieldLayerPatchRequest, FieldLayerResponse
from app.services.audit import write_audit_log

router = APIRouter(prefix="/v1/field-layers", tags=["field-layers"])


@router.get("", response_model=list[FieldLayerResponse])
def list_field_layers(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> list[FieldLayerResponse]:
    rows = db.execute(
        select(FieldLayer)
        .where(FieldLayer.is_active.is_(True))
        .order_by(FieldLayer.created_at.desc())
    ).scalars().all()
    return [FieldLayerResponse.model_validate(item) for item in rows]


@router.post("", response_model=FieldLayerResponse, status_code=status.HTTP_201_CREATED)
def create_field_layer(
    payload: FieldLayerCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> FieldLayerResponse:
    item = FieldLayer(
        name=payload.name.strip(),
        layer_type=payload.layer_type,
        geometry=payload.geometry,
        style=payload.style,
        is_active=payload.is_active,
        created_by=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="field_layer_create",
        entity_type="field_layer",
        entity_id=item.id,
        details={"name": item.name, "layer_type": item.layer_type.value},
    )
    return FieldLayerResponse.model_validate(item)


@router.patch("/{layer_id}", response_model=FieldLayerResponse)
def patch_field_layer(
    layer_id: str,
    payload: FieldLayerPatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> FieldLayerResponse:
    item = db.execute(select(FieldLayer).where(FieldLayer.id == layer_id)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saha katmani bulunamadi")

    changes = payload.model_dump(exclude_none=True)
    if payload.name is not None:
        item.name = payload.name.strip()
    if payload.layer_type is not None:
        item.layer_type = payload.layer_type
    if payload.geometry is not None:
        item.geometry = payload.geometry
    if payload.style is not None:
        item.style = payload.style
    if payload.is_active is not None:
        item.is_active = payload.is_active
    db.commit()
    db.refresh(item)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="field_layer_patch",
        entity_type="field_layer",
        entity_id=item.id,
        details=changes,
    )
    return FieldLayerResponse.model_validate(item)


@router.delete("/{layer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_field_layer(
    layer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
    _csrf_ok: None = Depends(require_csrf_for_cookie_auth),
) -> None:
    item = db.execute(select(FieldLayer).where(FieldLayer.id == layer_id)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saha katmani bulunamadi")

    details = {"name": item.name, "layer_type": item.layer_type.value}
    db.delete(item)
    db.commit()
    write_audit_log(
        db,
        actor_username=current_user.username,
        action="field_layer_delete",
        entity_type="field_layer",
        entity_id=layer_id,
        details=details,
    )

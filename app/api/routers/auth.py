from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_csrf_for_cookie_auth
from app.db.models import User
from app.db.session import get_db
from app.schemas.models import ChangePasswordRequest, ChangePasswordResponse, LoginRequest, TokenResponse
from app.security.auth import create_access_token, verify_password
from app.services.audit import write_audit_log
from app.services.passwords import apply_password_change, password_change_violation

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        write_audit_log(
            db,
            actor_username=payload.username,
            action="login_failed",
            entity_type="user",
            entity_id=payload.username,
            details={},
            success=False,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz kimlik bilgileri")

    if not user.is_active:
        write_audit_log(
            db,
            actor_username=payload.username,
            action="login_failed_inactive",
            entity_type="user",
            entity_id=user.id,
            details={},
            success=False,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")

    token = create_access_token(
        subject=user.username,
        role=user.role.value,
        pwd_reset_required=user.must_change_password,
    )
    write_audit_log(
        db,
        actor_username=user.username,
        action="login_success",
        entity_type="user",
        entity_id=user.id,
        details={},
        success=True,
    )
    return TokenResponse(
        access_token=token,
        role=user.role,
        password_change_required=user.must_change_password,
    )


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
    dependencies=[Depends(require_csrf_for_cookie_auth)],
)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChangePasswordResponse:
    violation = password_change_violation(
        current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    if violation == "bad_current_password":
        write_audit_log(
            db,
            actor_username=current_user.username,
            action="password_change_failed_bad_current",
            entity_type="user",
            entity_id=current_user.id,
            details={},
            success=False,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="current_password_invalid")

    if violation:
        write_audit_log(
            db,
            actor_username=current_user.username,
            action="password_change_failed_policy",
            entity_type="user",
            entity_id=current_user.id,
            details={"reason": violation},
            success=False,
        )
        if violation == "min_length":
            detail = "new_password_min_length_12"
        else:
            detail = "new_password_must_differ_from_current"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    apply_password_change(current_user, new_password=payload.new_password)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="password_change_success",
        entity_type="user",
        entity_id=current_user.id,
        details={},
        success=True,
    )
    return ChangePasswordResponse(username=current_user.username, password_change_required=False)

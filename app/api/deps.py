from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.security.auth import decode_access_token
from app.security.csrf import csrf_matches

settings = get_settings()


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token: str | None = None
    auth_via_cookie = False

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    else:
        cookie_token = request.cookies.get(settings.access_cookie_name)
        if cookie_token:
            token = cookie_token
            auth_via_cookie = True

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    username = payload.get("sub")
    role = payload.get("role")
    if not username or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")
    request.state.auth_via_cookie = auth_via_cookie
    return user


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.must_change_password:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password_change_required")
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker


def require_csrf_for_cookie_auth(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    authorization = request.headers.get("authorization", "")
    using_bearer = authorization.lower().startswith("bearer ")
    using_cookie = bool(request.cookies.get(settings.access_cookie_name))
    if using_cookie and not using_bearer:
        cookie_token = request.cookies.get(settings.csrf_cookie_name)
        if not csrf_matches(cookie_token, x_csrf_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")

from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Device, Drone, DroneKey, TrackState, User
from app.db.session import get_db
from app.domain.enums import DroneStatus, KeyStatus, PlatformRole, SignatureAlgorithm, UserRole
from app.security.auth import create_access_token, decode_access_token, verify_password
from app.security.crypto import encrypt_secret
from app.security.csrf import csrf_matches, new_csrf_token
from app.services.audit import write_audit_log
from app.services.drone_registry import delete_drone_from_registry
from app.services.login_rate_limit import client_identifier, login_rate_limiter
from app.services.passwords import apply_password_change, password_change_violation
from app.ui.text import get_ui_text

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(directory="app/ui/templates")
settings = get_settings()
UI_ERROR_CSRF = get_ui_text("common.errors.csrf_validation_failed")
UI_ERROR_PERMISSION_DENIED = get_ui_text("common.errors.permission_denied")

UNIT_CLASS_PREFIXES: dict[str, str] = {
    "piyade": "PY",
    "zirhli": "ZR",
    "topcu": "TP",
    "kesif": "KS",
    "komando": "KM",
}

UNIT_CLASS_LABELS: dict[str, str] = {
    "piyade": "Piyade",
    "zirhli": "Zırhlı",
    "topcu": "Topçu",
    "kesif": "Keşif",
    "komando": "Komando",
}

ROLE_LABELS: dict[UserRole, str] = {
    UserRole.admin: "Yönetici",
    UserRole.operator: "Operatör",
    UserRole.viewer: "Gözlemci",
}

PLATFORM_ROLE_LABELS: dict[str, str] = {
    PlatformRole.recon.value: "Keşif",
    PlatformRole.interceptor.value: "Önleyici",
}

DRONE_STATUS_LABELS: dict[str, str] = {
    DroneStatus.active.value: "Aktif",
    DroneStatus.inactive.value: "Pasif",
}


def _asset_version() -> str:
    static_files = [
        Path("app/ui/static/css/tactical.css"),
        Path("app/ui/static/vendor/leaflet/leaflet.css"),
        Path("app/ui/static/vendor/leaflet/leaflet.js"),
        Path("app/ui/static/js/ui_csrf.js"),
        Path("app/ui/static/js/track_map.js"),
        Path("app/ui/static/js/control_center.js"),
        Path("app/ui/static/css/control_center_demo.css"),
        Path("app/ui/static/js/operator.js"),
        Path("app/ui/static/js/drone_registry.js"),
    ]
    mtimes: list[int] = []
    for item in static_files:
        try:
            mtimes.append(int(item.stat().st_mtime))
        except OSError:
            continue
    return str(max(mtimes) if mtimes else 1)


def _ui_context(**extra: object) -> dict[str, object]:
    context: dict[str, object] = {
        "asset_version": _asset_version(),
        "csrf_cookie_name": settings.csrf_cookie_name,
        "map_config": _map_config(),
        "demo_mode_enabled": settings.demo_mode_enabled,
    }
    context.update(extra)
    return context


def _map_config() -> dict[str, object]:
    use_vector_basemap = settings.map_provider == "openfreemap"
    return {
        "provider": settings.map_provider,
        "use_vector_basemap": use_vector_basemap,
        "style_url": settings.map_style_url,
        "label_language": settings.map_label_language,
        "hidden_labels": [
            item.strip()
            for item in settings.map_hidden_labels.split(",")
            if item.strip()
        ],
        "home_center": [settings.map_home_lat, settings.map_home_lon],
        "home_zoom": settings.map_home_zoom,
        "min_zoom": settings.map_min_zoom,
        "max_zoom": settings.map_max_zoom,
        "maplibre_css_url": settings.maplibre_css_url,
        "maplibre_js_url": settings.maplibre_js_url,
        "maplibre_leaflet_js_url": settings.maplibre_leaflet_js_url,
    }


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


def _new_key_id() -> str:
    return f"key-{uuid4().hex[:16]}"


def _normalize_unit_class(value: str) -> str:
    return value.strip().lower()


def _prefix_for_unit_class(unit_class: str) -> str | None:
    return UNIT_CLASS_PREFIXES.get(_normalize_unit_class(unit_class))


def _next_uid_for_prefix(db: Session, prefix: str) -> str:
    rows = db.execute(select(Drone.drone_uid).where(Drone.drone_uid.like(f"{prefix}-%"))).scalars().all()
    max_number = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for uid in rows:
        match = pattern.match(uid)
        if not match:
            continue
        max_number = max(max_number, int(match.group(1)))
    return f"{prefix}-{max_number + 1:03d}"


def _set_csrf_cookie(response: HTMLResponse | RedirectResponse, csrf_token: str) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.session_max_age_seconds,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )


def _set_access_cookie(response: HTMLResponse | RedirectResponse, access_token: str) -> None:
    response.set_cookie(
        key=settings.access_cookie_name,
        value=access_token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )


def _clear_auth_cookies(response: HTMLResponse | RedirectResponse) -> None:
    response.delete_cookie(settings.access_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def _get_ui_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(settings.access_cookie_name)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


def _default_ui_target(user: User) -> str:
    if user.role == UserRole.operator:
        return "/ui/operator"
    return "/ui/control-center"


def _render_change_password_page(
    request: Request,
    *,
    username: str,
    csrf_token: str,
    error: str | None,
    status_code: int,
) -> HTMLResponse:
    response = templates.TemplateResponse(
        request=request,
        name="change_password.html",
        context=_ui_context(username=username, error=error, csrf_token=csrf_token),
        status_code=status_code,
    )
    _set_csrf_cookie(response, csrf_token)
    return response


def _render_drone_registry_page(
    request: Request,
    *,
    db: Session,
    current_user: User,
    csrf_token: str,
    drones: list[Drone],
    unit_class: str,
    suggested_uid: str,
    error: str | None = None,
    success: str | None = None,
    provisioned: dict[str, str] | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    track_by_uid = {item.drone_uid: item for item in db.execute(select(TrackState)).scalars().all()}
    devices_by_drone_id: dict[str, list[Device]] = {}
    for device in db.execute(select(Device).order_by(Device.updated_at.desc())).scalars().all():
        devices_by_drone_id.setdefault(device.drone_id, []).append(device)
    response = templates.TemplateResponse(
        request=request,
        name="drone_registry.html",
        context=_ui_context(
            username=current_user.username,
            role=current_user.role.value,
            role_label=ROLE_LABELS[current_user.role],
            csrf_token=csrf_token,
            drones=drones,
            unit_class=unit_class,
            unit_classes=[{"value": key, "label": UNIT_CLASS_LABELS[key]} for key in UNIT_CLASS_PREFIXES],
            suggested_uid=suggested_uid,
            platform_roles=[PlatformRole.recon.value, PlatformRole.interceptor.value],
            platform_role_labels=PLATFORM_ROLE_LABELS,
            drone_status_labels=DRONE_STATUS_LABELS,
            track_by_uid=track_by_uid,
            devices_by_drone_id=devices_by_drone_id,
            default_home=_default_ui_target(current_user),
            error=error,
            success=success,
            provisioned=provisioned,
        ),
        status_code=status_code,
    )
    _set_csrf_cookie(response, csrf_token)
    return response


def _policy_error_message(violation: str) -> str:
    if violation == "min_length":
        return "Yeni parola en az 12 karakter olmalı."
    if violation == "same_as_current":
        return "Yeni parola mevcut parola ile aynı olamaz."
    return "Parola politikası ihlali."


@router.get("/login", response_class=HTMLResponse)
def ui_login_page(request: Request) -> HTMLResponse:
    csrf_token = new_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="login.html",
        context=_ui_context(error=None, csrf_token=csrf_token),
        status_code=status.HTTP_200_OK,
    )
    _set_csrf_cookie(response, csrf_token)
    return response


@router.post("/login", response_class=HTMLResponse)
def ui_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    cookie_csrf = request.cookies.get(settings.csrf_cookie_name)
    if not csrf_matches(cookie_csrf, csrf_token):
        csrf_new = new_csrf_token()
        response = templates.TemplateResponse(
            request=request,
            name="login.html",
            context=_ui_context(error=UI_ERROR_CSRF, csrf_token=csrf_new),
            status_code=status.HTTP_403_FORBIDDEN,
        )
        _set_csrf_cookie(response, csrf_new)
        return response

    client_id = client_identifier(request)
    if login_rate_limiter.is_blocked(client_id):
        write_audit_log(
            db,
            actor_username=username,
            action="ui_login_rate_limited",
            entity_type="user",
            entity_id=username,
            details={},
            success=False,
        )
        csrf_new = new_csrf_token()
        response = templates.TemplateResponse(
            request=request,
            name="login.html",
            context=_ui_context(
                error="Çok fazla başarısız giriş denemesi. Lütfen bir süre sonra tekrar deneyin.",
                csrf_token=csrf_new,
            ),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        _set_csrf_cookie(response, csrf_new)
        return response

    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        login_rate_limiter.register_failure(client_id)
        write_audit_log(
            db,
            actor_username=username,
            action="ui_login_failed",
            entity_type="user",
            entity_id=username,
            details={},
            success=False,
        )
        csrf_new = new_csrf_token()
        response = templates.TemplateResponse(
            request=request,
            name="login.html",
            context=_ui_context(error="Kullanıcı adı veya parola hatalı", csrf_token=csrf_new),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        _set_csrf_cookie(response, csrf_new)
        return response

    if not user.is_active:
        csrf_new = new_csrf_token()
        response = templates.TemplateResponse(
            request=request,
            name="login.html",
            context=_ui_context(error="Kullanıcı pasif durumda", csrf_token=csrf_new),
            status_code=status.HTTP_403_FORBIDDEN,
        )
        _set_csrf_cookie(response, csrf_new)
        return response

    login_rate_limiter.reset(client_id)
    token = create_access_token(
        subject=user.username,
        role=user.role.value,
        pwd_reset_required=user.must_change_password,
    )
    write_audit_log(
        db,
        actor_username=user.username,
        action="ui_login_success",
        entity_type="user",
        entity_id=user.id,
        details={},
        success=True,
    )

    csrf_new = new_csrf_token()
    target = "/ui/change-password" if user.must_change_password else _default_ui_target(user)
    response = RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
    _set_access_cookie(response, token)
    _set_csrf_cookie(response, csrf_new)
    return response


@router.post("/logout")
def ui_logout(request: Request, csrf_token: str = Form(...)) -> RedirectResponse:
    cookie_csrf = request.cookies.get(settings.csrf_cookie_name)
    response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
    if not csrf_matches(cookie_csrf, csrf_token):
        _clear_auth_cookies(response)
        return response
    _clear_auth_cookies(response)
    return response


@router.get("/change-password", response_class=HTMLResponse)
def ui_change_password_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    user = _get_ui_user(request, db)
    if not user:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
        _clear_auth_cookies(response)
        return response
    if not user.must_change_password:
        return RedirectResponse(url=_default_ui_target(user), status_code=status.HTTP_302_FOUND)

    csrf_token = request.cookies.get(settings.csrf_cookie_name) or new_csrf_token()
    return _render_change_password_page(
        request,
        username=user.username,
        csrf_token=csrf_token,
        error=None,
        status_code=status.HTTP_200_OK,
    )


@router.post("/change-password", response_class=HTMLResponse)
def ui_change_password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    cookie_csrf = request.cookies.get(settings.csrf_cookie_name)
    user = _get_ui_user(request, db)
    if not user:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
        _clear_auth_cookies(response)
        return response
    if not user.must_change_password:
        return RedirectResponse(url=_default_ui_target(user), status_code=status.HTTP_302_FOUND)

    if not csrf_matches(cookie_csrf, csrf_token):
        csrf_new = new_csrf_token()
        return _render_change_password_page(
            request,
            username=user.username,
            csrf_token=csrf_new,
            error=UI_ERROR_CSRF,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if new_password != confirm_password:
        csrf_new = new_csrf_token()
        return _render_change_password_page(
            request,
            username=user.username,
            csrf_token=csrf_new,
            error="Yeni parola ve doğrulama eşleşmiyor.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    violation = password_change_violation(user, current_password=current_password, new_password=new_password)
    if violation == "bad_current_password":
        csrf_new = new_csrf_token()
        return _render_change_password_page(
            request,
            username=user.username,
            csrf_token=csrf_new,
            error="Mevcut parola hatalı.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if violation:
        csrf_new = new_csrf_token()
        return _render_change_password_page(
            request,
            username=user.username,
            csrf_token=csrf_new,
            error=_policy_error_message(violation),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    apply_password_change(user, new_password=new_password)
    db.add(user)
    db.commit()
    db.refresh(user)

    write_audit_log(
        db,
        actor_username=user.username,
        action="password_change_success",
        entity_type="user",
        entity_id=user.id,
        details={},
        success=True,
    )

    token = create_access_token(subject=user.username, role=user.role.value, pwd_reset_required=False)
    csrf_new = new_csrf_token()
    response = RedirectResponse(url=_default_ui_target(user), status_code=status.HTTP_302_FOUND)
    _set_access_cookie(response, token)
    _set_csrf_cookie(response, csrf_new)
    return response


@router.get("/drones/next-uid")
def ui_drones_next_uid(
    request: Request,
    unit_class: str = Query("piyade"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    current_user = _get_ui_user(request, db)
    if not current_user:
        return JSONResponse({"detail": "Yetkisiz erişim"}, status_code=status.HTTP_401_UNAUTHORIZED)
    if current_user.must_change_password:
        return JSONResponse({"detail": "password_change_required"}, status_code=status.HTTP_403_FORBIDDEN)

    normalized = _normalize_unit_class(unit_class)
    prefix = _prefix_for_unit_class(normalized)
    if not prefix:
        return JSONResponse({"detail": "invalid_unit_class"}, status_code=status.HTTP_400_BAD_REQUEST)

    return JSONResponse(
        {"unit_class": normalized, "prefix": prefix, "drone_uid": _next_uid_for_prefix(db, prefix)},
        status_code=status.HTTP_200_OK,
    )


@router.get("/drones", response_class=HTMLResponse)
def ui_drones_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    current_user = _get_ui_user(request, db)
    if not current_user:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
        _clear_auth_cookies(response)
        return response
    if current_user.must_change_password:
        return RedirectResponse(url="/ui/change-password", status_code=status.HTTP_302_FOUND)

    default_unit_class = next(iter(UNIT_CLASS_PREFIXES))
    suggested_uid = _next_uid_for_prefix(db, UNIT_CLASS_PREFIXES[default_unit_class])
    csrf_token = request.cookies.get(settings.csrf_cookie_name) or new_csrf_token()
    drones = db.execute(select(Drone).order_by(Drone.created_at.desc())).scalars().all()
    return _render_drone_registry_page(
        request,
        db=db,
        current_user=current_user,
        csrf_token=csrf_token,
        drones=drones,
        unit_class=default_unit_class,
        suggested_uid=suggested_uid,
    )


@router.post("/drones", response_class=HTMLResponse)
def ui_drones_submit(
    request: Request,
    unit_class: str = Form(...),
    drone_uid: str = Form(""),
    platform_role: str = Form("recon"),
    status_value: str = Form("active"),
    shared_secret: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    current_user = _get_ui_user(request, db)
    if not current_user:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
        _clear_auth_cookies(response)
        return response
    if current_user.must_change_password:
        return RedirectResponse(url="/ui/change-password", status_code=status.HTTP_302_FOUND)

    normalized_unit_class = _normalize_unit_class(unit_class)
    prefix = _prefix_for_unit_class(normalized_unit_class) or UNIT_CLASS_PREFIXES[next(iter(UNIT_CLASS_PREFIXES))]
    suggested_uid = _next_uid_for_prefix(db, prefix)
    csrf_new = new_csrf_token()
    drones = db.execute(select(Drone).order_by(Drone.created_at.desc())).scalars().all()

    if not csrf_matches(request.cookies.get(settings.csrf_cookie_name), csrf_token):
        return _render_drone_registry_page(
            request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_new,
            drones=drones,
            unit_class=normalized_unit_class,
            suggested_uid=suggested_uid,
            error=UI_ERROR_CSRF,
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if current_user.role not in {UserRole.admin, UserRole.operator}:
        return _render_drone_registry_page(
            request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_new,
            drones=drones,
            unit_class=normalized_unit_class,
            suggested_uid=suggested_uid,
            error=UI_ERROR_PERMISSION_DENIED,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    clean_uid = drone_uid.strip() or suggested_uid
    try:
        clean_role = PlatformRole(platform_role.strip())
        clean_status = DroneStatus(status_value.strip())
    except ValueError:
        return _render_drone_registry_page(
            request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_new,
            drones=drones,
            unit_class=normalized_unit_class,
            suggested_uid=suggested_uid,
            error="Drone rolü veya durumu geçersiz.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    shared = shared_secret.strip() or _new_secret()
    key = DroneKey(
        key_id=_new_key_id(),
        algo=SignatureAlgorithm.hmac_sha256_v1,
        secret_enc=encrypt_secret(shared),
        status=KeyStatus.active,
    )
    db.add(key)
    db.flush()

    drone = Drone(
        drone_uid=clean_uid,
        unit=UNIT_CLASS_LABELS.get(normalized_unit_class, normalized_unit_class.title()),
        platform_role=clean_role,
        status=clean_status,
        key_id=key.id,
    )
    db.add(drone)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        drones = db.execute(select(Drone).order_by(Drone.created_at.desc())).scalars().all()
        suggested_uid = _next_uid_for_prefix(db, prefix)
        return _render_drone_registry_page(
            request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_new,
            drones=drones,
            unit_class=normalized_unit_class,
            suggested_uid=suggested_uid,
            error="Drone kimliği zaten kayıtlı.",
            status_code=status.HTTP_409_CONFLICT,
        )
    db.refresh(drone)

    write_audit_log(
        db,
        actor_username=current_user.username,
        action="drone_create",
        entity_type="drone",
        entity_id=drone.id,
        details={"drone_uid": drone.drone_uid, "platform_role": drone.platform_role.value, "via": "ui"},
    )
    drones = db.execute(select(Drone).order_by(Drone.created_at.desc())).scalars().all()
    suggested_uid = _next_uid_for_prefix(db, prefix)
    return _render_drone_registry_page(
        request,
        db=db,
        current_user=current_user,
        csrf_token=csrf_new,
        drones=drones,
        unit_class=normalized_unit_class,
        suggested_uid=suggested_uid,
        success=f"{drone.drone_uid} eklendi.",
        provisioned={"drone_uid": drone.drone_uid, "key_id": key.key_id, "shared_secret": shared},
        status_code=status.HTTP_201_CREATED,
    )


@router.post("/drones/{drone_id}/delete", response_class=HTMLResponse)
def ui_drones_delete(
    request: Request,
    drone_id: str,
    unit_class: str = Form("piyade"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    current_user = _get_ui_user(request, db)
    if not current_user:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
        _clear_auth_cookies(response)
        return response
    if current_user.must_change_password:
        return RedirectResponse(url="/ui/change-password", status_code=status.HTTP_302_FOUND)

    normalized_unit_class = _normalize_unit_class(unit_class)
    prefix = _prefix_for_unit_class(normalized_unit_class) or UNIT_CLASS_PREFIXES[next(iter(UNIT_CLASS_PREFIXES))]
    suggested_uid = _next_uid_for_prefix(db, prefix)
    csrf_new = new_csrf_token()
    drones = db.execute(select(Drone).order_by(Drone.created_at.desc())).scalars().all()

    if not csrf_matches(request.cookies.get(settings.csrf_cookie_name), csrf_token):
        return _render_drone_registry_page(
            request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_new,
            drones=drones,
            unit_class=normalized_unit_class,
            suggested_uid=suggested_uid,
            error=UI_ERROR_CSRF,
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if current_user.role not in {UserRole.admin, UserRole.operator}:
        return _render_drone_registry_page(
            request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_new,
            drones=drones,
            unit_class=normalized_unit_class,
            suggested_uid=suggested_uid,
            error=UI_ERROR_PERMISSION_DENIED,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    result = delete_drone_from_registry(db, drone_id=drone_id, actor_username=current_user.username, via="ui")
    drones = db.execute(select(Drone).order_by(Drone.created_at.desc())).scalars().all()
    if result.ok:
        return _render_drone_registry_page(
            request,
            db=db,
            current_user=current_user,
            csrf_token=csrf_new,
            drones=drones,
            unit_class=normalized_unit_class,
            suggested_uid=suggested_uid,
            success=f"{result.drone_uid} silindi.",
        )

    if result.reason == "linked_operator_station":
        error = "Drone bir operatör istasyonuna bağlı olduğu için silinemiyor."
        code = status.HTTP_409_CONFLICT
    elif result.reason == "has_devices":
        error = "Drone üzerinde bağlı cihaz kaydı var, önce cihaz bağını kaldırın."
        code = status.HTTP_409_CONFLICT
    elif result.reason == "not_found":
        error = "Drone kaydı bulunamadı."
        code = status.HTTP_404_NOT_FOUND
    else:
        error = "Drone silme işlemi başarısız."
        code = status.HTTP_400_BAD_REQUEST

    return _render_drone_registry_page(
        request,
        db=db,
        current_user=current_user,
        csrf_token=csrf_new,
        drones=drones,
        unit_class=normalized_unit_class,
        suggested_uid=suggested_uid,
        error=error,
        status_code=code,
    )


def _render_control_center(
    request: Request,
    db: Session,
    template_name: str,
) -> HTMLResponse:
    current_user = _get_ui_user(request, db)
    if not current_user:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
        _clear_auth_cookies(response)
        return response
    if current_user.must_change_password:
        return RedirectResponse(url="/ui/change-password", status_code=status.HTTP_302_FOUND)
    if current_user.role == UserRole.operator:
        return RedirectResponse(url="/ui/operator", status_code=status.HTTP_302_FOUND)

    csrf_token = request.cookies.get(settings.csrf_cookie_name) or new_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name=template_name,
        context=_ui_context(
            username=current_user.username,
            role=current_user.role.value,
            role_label=ROLE_LABELS[current_user.role],
            csrf_token=csrf_token,
            readonly=current_user.role == UserRole.viewer,
        ),
        status_code=status.HTTP_200_OK,
    )
    _set_csrf_cookie(response, csrf_token)
    return response


@router.get("/control-center", response_class=HTMLResponse)
def ui_control_center(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _render_control_center(request, db, "control_center_demo.html")


@router.get("/control-center-demo")
def ui_control_center_demo() -> RedirectResponse:
    return RedirectResponse(url="/ui/control-center", status_code=status.HTTP_302_FOUND)


@router.get("/operator", response_class=HTMLResponse)
def ui_operator(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    current_user = _get_ui_user(request, db)
    if not current_user:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
        _clear_auth_cookies(response)
        return response
    if current_user.must_change_password:
        return RedirectResponse(url="/ui/change-password", status_code=status.HTTP_302_FOUND)
    if current_user.role not in {UserRole.admin, UserRole.operator}:
        return RedirectResponse(url="/ui/control-center", status_code=status.HTTP_302_FOUND)

    csrf_token = request.cookies.get(settings.csrf_cookie_name) or new_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="operator.html",
        context=_ui_context(
            username=current_user.username,
            role=current_user.role.value,
            role_label=ROLE_LABELS[current_user.role],
            csrf_token=csrf_token,
            is_admin_preview=current_user.role == UserRole.admin,
        ),
        status_code=status.HTTP_200_OK,
    )
    _set_csrf_cookie(response, csrf_token)
    return response


@router.get("/tactical", response_class=HTMLResponse)
def ui_tactical_redirect(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    current_user = _get_ui_user(request, db)
    if not current_user:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
        _clear_auth_cookies(response)
        return response
    if current_user.must_change_password:
        return RedirectResponse(url="/ui/change-password", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url=_default_ui_target(current_user), status_code=status.HTTP_302_FOUND)


@router.get("/missions", response_class=HTMLResponse)
def ui_missions_redirect(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    current_user = _get_ui_user(request, db)
    if not current_user:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_302_FOUND)
        _clear_auth_cookies(response)
        return response
    if current_user.must_change_password:
        return RedirectResponse(url="/ui/change-password", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/ui/control-center", status_code=status.HTTP_302_FOUND)

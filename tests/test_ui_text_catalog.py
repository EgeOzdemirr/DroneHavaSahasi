from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import ui
from app.config import get_settings
from app.db.base import Base
from app.db.models import User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.security.auth import hash_password
from app.ui.text import build_ui_text_bundle, get_ui_text


def _build_testbed() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(ui.router)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_factory


def _create_user(session_factory: sessionmaker, *, username: str = "admin", role: UserRole = UserRole.admin) -> None:
    with session_factory() as db:
        db.add(
            User(
                username=username,
                password_hash=hash_password("AdminPass-12345"),
                role=role,
                is_active=True,
                must_change_password=False,
            )
        )
        db.commit()


def _ui_login(client: TestClient) -> None:
    settings = get_settings()
    login_page = client.get("/ui/login")
    assert login_page.status_code == 200
    csrf = client.cookies.get(settings.csrf_cookie_name)

    login_submit = client.post(
        "/ui/login",
        data={"username": "admin", "password": "AdminPass-12345", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert login_submit.status_code == 302
    assert login_submit.headers["location"] == "/ui/control-center"


def test_ui_text_catalog_supports_namespaced_lookup() -> None:
    bundle = build_ui_text_bundle("common")
    assert bundle["common"]["errors"]["permission_denied"] == "Bu işlem için yetkiniz yok."
    assert get_ui_text("common.errors.csrf_validation_failed") == "CSRF doğrulaması başarısız."


def test_control_center_page_renders_after_login_and_tactical_redirects() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory)
    _ui_login(client)

    redirect = client.get("/ui/tactical", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "/ui/control-center"

    response = client.get("/ui/control-center")
    assert response.status_code == 200
    assert "control-demo-shell" in response.text
    assert "control_center_demo.css" in response.text
    assert "KONTROL MERKEZİ" in response.text
    assert "Operatör İstasyonları" in response.text
    assert "Hedef Tespitleri" in response.text
    assert "toggle-map-target-picker" in response.text
    assert "confirm-map-target" in response.text
    assert "Hedef Ekle" in response.text
    assert "Hedefi Onayla" in response.text
    assert "toggle-air-traffic" in response.text
    assert "Sivil Hava Trafiğini Aktif Et" in response.text
    assert "field-layer-form" in response.text
    assert "field-layer-draft-status" in response.text
    assert "field-layer-undo" not in response.text
    assert "control-replay-panel" in response.text
    assert "control-progress-panel" in response.text
    assert "task-timeline" in response.text
    assert "/ui/static/vendor/leaflet/leaflet.css" in response.text
    assert "/ui/static/vendor/leaflet/leaflet.js" in response.text
    assert "/ui/static/js/track_map.js" in response.text


def test_control_center_demo_redirects_to_main_control_center_after_login() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory)
    _ui_login(client)

    response = client.get("/ui/control-center-demo", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/ui/control-center"


def test_operator_page_renders_real_map_assets_after_login() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory, username="operator1", role=UserRole.operator)

    settings = get_settings()
    login_page = client.get("/ui/login")
    assert login_page.status_code == 200
    csrf = client.cookies.get(settings.csrf_cookie_name)

    login_submit = client.post(
        "/ui/login",
        data={"username": "operator1", "password": "AdminPass-12345", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert login_submit.status_code == 302
    assert login_submit.headers["location"] == "/ui/operator"

    response = client.get("/ui/operator")
    assert response.status_code == 200
    assert "OPERATÖR PANELİ" in response.text
    assert "operator-map-canvas" in response.text
    assert "operator-replay-panel" in response.text
    assert "operator-progress-panel" in response.text
    assert "/ui/static/vendor/leaflet/leaflet.css" in response.text
    assert "/ui/static/vendor/leaflet/leaflet.js" in response.text
    assert "/ui/static/js/track_map.js" in response.text

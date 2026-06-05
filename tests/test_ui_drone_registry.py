from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import ui
from app.config import get_settings
from app.db.base import Base
from app.db.models import Drone, DroneKey, OperatorStation, User
from app.db.session import get_db
from app.domain.enums import DroneStatus, KeyStatus, PlatformRole, SignatureAlgorithm, UserRole
from app.security.auth import hash_password
from app.security.crypto import encrypt_secret


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


def _create_user(session_factory: sessionmaker, *, username: str, role: UserRole) -> None:
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


def _ui_login(client: TestClient, *, username: str, expected_target: str) -> None:
    settings = get_settings()
    login_page = client.get("/ui/login")
    assert login_page.status_code == 200
    csrf = client.cookies.get(settings.csrf_cookie_name)
    assert csrf

    login_submit = client.post(
        "/ui/login",
        data={"username": username, "password": "AdminPass-12345", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert login_submit.status_code == 302
    assert login_submit.headers["location"] == expected_target


def test_admin_can_create_drone_with_auto_uid_increment_and_role() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory, username="admin", role=UserRole.admin)
    _ui_login(client, username="admin", expected_target="/ui/control-center")
    settings = get_settings()

    registry = client.get("/ui/drones")
    assert registry.status_code == 200
    assert "PY-001" in registry.text

    csrf = client.cookies.get(settings.csrf_cookie_name)
    first_resp = client.post(
        "/ui/drones",
        data={
            "unit_class": "piyade",
            "drone_uid": "",
            "platform_role": "recon",
            "status_value": "active",
            "shared_secret": "",
            "csrf_token": csrf,
        },
    )
    assert first_resp.status_code == 201
    assert "PY-001" in first_resp.text
    assert "Keşif" in first_resp.text
    assert "drone-card-grid" in first_resp.text
    assert "drone-registry-card" in first_resp.text
    assert "Son Telemetri" in first_resp.text
    assert "Cihaz" in first_resp.text

    csrf = client.cookies.get(settings.csrf_cookie_name)
    second_resp = client.post(
        "/ui/drones",
        data={
            "unit_class": "piyade",
            "drone_uid": "",
            "platform_role": "interceptor",
            "status_value": "active",
            "shared_secret": "",
            "csrf_token": csrf,
        },
    )
    assert second_resp.status_code == 201
    assert "PY-002" in second_resp.text
    assert "Önleyici" in second_resp.text

    with session_factory() as db:
        first = db.execute(select(Drone).where(Drone.drone_uid == "PY-001")).scalar_one()
        second = db.execute(select(Drone).where(Drone.drone_uid == "PY-002")).scalar_one()
        assert first.platform_role == PlatformRole.recon
        assert second.platform_role == PlatformRole.interceptor


def test_next_uid_endpoint_returns_expected_prefix() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory, username="admin", role=UserRole.admin)
    _ui_login(client, username="admin", expected_target="/ui/control-center")

    first = client.get("/ui/drones/next-uid?unit_class=topcu")
    assert first.status_code == 200
    assert first.json()["drone_uid"] == "TP-001"


def test_viewer_cannot_create_drone_from_ui_registry() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory, username="viewer", role=UserRole.viewer)
    _ui_login(client, username="viewer", expected_target="/ui/control-center")
    settings = get_settings()
    csrf = client.cookies.get(settings.csrf_cookie_name)

    create_resp = client.post(
        "/ui/drones",
        data={
            "unit_class": "zirhli",
            "drone_uid": "",
            "platform_role": "recon",
            "status_value": "active",
            "shared_secret": "",
            "csrf_token": csrf,
        },
    )
    assert create_resp.status_code == 403
    assert "yetkiniz yok" in create_resp.text.lower()


def test_admin_can_delete_drone_from_ui_registry() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory, username="admin", role=UserRole.admin)
    _ui_login(client, username="admin", expected_target="/ui/control-center")
    settings = get_settings()

    csrf = client.cookies.get(settings.csrf_cookie_name)
    create_resp = client.post(
        "/ui/drones",
        data={
            "unit_class": "komando",
            "drone_uid": "",
            "platform_role": "recon",
            "status_value": "active",
            "shared_secret": "",
            "csrf_token": csrf,
        },
    )
    assert create_resp.status_code == 201

    with session_factory() as db:
        drone = db.execute(select(Drone).where(Drone.drone_uid == "KM-001")).scalar_one()
        drone_id = drone.id

    csrf = client.cookies.get(settings.csrf_cookie_name)
    delete_resp = client.post(f"/ui/drones/{drone_id}/delete", data={"unit_class": "komando", "csrf_token": csrf})
    assert delete_resp.status_code == 200
    assert "KM-001 silindi" in delete_resp.text


def test_delete_blocked_when_drone_is_linked_to_operator_station() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory, username="admin", role=UserRole.admin)
    _create_user(session_factory, username="operator1", role=UserRole.operator)
    _ui_login(client, username="admin", expected_target="/ui/control-center")

    with session_factory() as db:
        key = DroneKey(
            key_id="key-blocked-1-external",
            algo=SignatureAlgorithm.hmac_sha256_v1,
            secret_enc=encrypt_secret("enc" * 12),
            status=KeyStatus.active,
        )
        db.add(key)
        db.flush()
        drone = Drone(
            drone_uid="PY-200",
            unit="Piyade",
            platform_role=PlatformRole.interceptor,
            status=DroneStatus.active,
            key_id=key.id,
        )
        db.add(drone)
        db.flush()
        operator_user = db.execute(select(User).where(User.username == "operator1")).scalar_one()
        db.add(
            OperatorStation(
                user_id=operator_user.id,
                name="OS-200",
                lat=41.0,
                lon=29.0,
                assigned_interceptor_drone_id=drone.id,
                is_active=True,
            )
        )
        db.commit()
        drone_id = drone.id

    settings = get_settings()
    csrf = client.cookies.get(settings.csrf_cookie_name)
    delete_resp = client.post(
        f"/ui/drones/{drone_id}/delete",
        data={"unit_class": "piyade", "csrf_token": csrf},
    )
    assert delete_resp.status_code == 409
    assert "operatör istasyonuna bağlı" in delete_resp.text.lower()

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import auth, drones
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
    app.include_router(auth.router)
    app.include_router(drones.router)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_factory


def _seed_user(session_factory: sessionmaker, *, username: str, role: UserRole) -> None:
    with session_factory() as db:
        db.add(User(username=username, password_hash=hash_password("AdminPass-12345"), role=role, is_active=True))
        db.commit()


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/v1/auth/login", json={"username": "admin", "password": "AdminPass-12345"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_delete_drone_success() -> None:
    client, session_factory = _build_testbed()
    _seed_user(session_factory, username="admin", role=UserRole.admin)
    headers = _auth_headers(client)

    create = client.post(
        "/v1/drones",
        headers=headers,
        json={
            "drone_uid": "DRN-DEL-001",
            "unit": "Piyade",
            "platform_role": "recon",
            "status": "active",
            "shared_secret": "s" * 24,
        },
    )
    assert create.status_code == 201
    drone_id = create.json()["drone"]["id"]

    delete = client.delete(f"/v1/drones/{drone_id}", headers=headers)
    assert delete.status_code == 204

    listed = client.get("/v1/drones", headers=headers)
    assert listed.status_code == 200
    assert all(item["id"] != drone_id for item in listed.json())


def test_delete_drone_blocked_when_assigned_to_operator_station() -> None:
    client, session_factory = _build_testbed()
    _seed_user(session_factory, username="admin", role=UserRole.admin)
    _seed_user(session_factory, username="operator1", role=UserRole.operator)
    headers = _auth_headers(client)

    with session_factory() as db:
        key = DroneKey(
            key_id="key-del-blocked",
            algo=SignatureAlgorithm.hmac_sha256_v1,
            secret_enc=encrypt_secret("x" * 32),
            status=KeyStatus.active,
        )
        db.add(key)
        db.flush()
        drone = Drone(
            drone_uid="DRN-DEL-002",
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
                name="OS-1",
                lat=41.0,
                lon=29.0,
                assigned_interceptor_drone_id=drone.id,
                is_active=True,
            )
        )
        db.commit()
        drone_id = drone.id

    delete = client.delete(f"/v1/drones/{drone_id}", headers=headers)
    assert delete.status_code == 409
    assert "operatör istasyonuna bağlı" in delete.json()["detail"]

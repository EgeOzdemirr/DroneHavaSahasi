from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import auth, devices, telemetry
from app.db.base import Base
from app.db.models import AuditLog, Device, Drone, DroneKey, User
from app.db.session import get_db
from app.domain.enums import DroneStatus, KeyStatus, PlatformRole, SignatureAlgorithm, UserRole
from app.schemas.models import TelemetryPayload
from app.security.auth import hash_password
from app.security.crypto import encrypt_secret
from app.security.hmac_signatures import body_sha256_hex, canonical_signing_input, sign_hmac_hex


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
    app.include_router(devices.router)
    app.include_router(telemetry.router)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_factory


def _seed_user(db: Session, *, username: str, role: UserRole) -> User:
    user = User(
        username=username,
        password_hash=hash_password("Pass-For-Tests-123"),
        role=role,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user


def _seed_drone(db: Session, *, drone_uid: str, shared_secret: str, platform_role: PlatformRole) -> Drone:
    key = DroneKey(
        key_id=f"key-{drone_uid.lower()}",
        algo=SignatureAlgorithm.hmac_sha256_v1,
        secret_enc=encrypt_secret(shared_secret),
        status=KeyStatus.active,
    )
    db.add(key)
    db.flush()

    drone = Drone(
        drone_uid=drone_uid,
        unit="alpha",
        platform_role=platform_role,
        status=DroneStatus.active,
        key_id=key.id,
    )
    db.add(drone)
    db.commit()
    db.refresh(drone)
    return drone


def _login(client: TestClient, username: str) -> str:
    response = client.post("/v1/auth/login", json={"username": username, "password": "Pass-For-Tests-123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def _signed_headers(
    *,
    drone_uid: str,
    shared_secret: str,
    nonce: str,
    raw_body: bytes,
    bad_signature: bool = False,
    device_id: str | None = None,
) -> dict[str, str]:
    ts_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    digest = body_sha256_hex(raw_body)
    canonical = canonical_signing_input(drone_uid, ts_ms, nonce, digest)
    signature = sign_hmac_hex(shared_secret, canonical)
    if bad_signature:
        first = "0" if signature[0] != "0" else "1"
        signature = f"{first}{signature[1:]}"
    headers = {
        "X-Drone-Uid": drone_uid,
        "X-Ts": ts_ms,
        "X-Nonce": nonce,
        "X-Signature": signature,
        "X-Sig-Version": "hmac-sha256-v1",
    }
    if device_id:
        headers["X-Device-Id"] = device_id
    return headers


def test_device_provision_rotate_and_health_flow() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        _seed_drone(db, drone_uid="DEV-DRN-001", shared_secret="dev-secret-001", platform_role=PlatformRole.recon)

    token = _login(client, "admin")
    headers = {"Authorization": f"Bearer {token}"}

    provision = client.post(
        "/v2/devices/provision",
        headers=headers,
        json={"device_id": "JETSON-001", "drone_uid": "DEV-DRN-001", "cert_fingerprint": "sha256:ABC123"},
    )
    assert provision.status_code == 201
    assert provision.json()["drone_uid"] == "DEV-DRN-001"

    health = client.get("/v2/devices/JETSON-001/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["health"] == "never_seen"

    same_rotate = client.post(
        "/v2/devices/JETSON-001/rotate-cert",
        headers=headers,
        json={"cert_fingerprint": "sha256:ABC123"},
    )
    assert same_rotate.status_code == 400

    rotate = client.post(
        "/v2/devices/JETSON-001/rotate-cert",
        headers=headers,
        json={"cert_fingerprint": "sha256:XYZ789"},
    )
    assert rotate.status_code == 200

    with session_factory() as db:
        actions = db.execute(
            select(AuditLog.action).where(AuditLog.entity_type == "device").order_by(AuditLog.created_at.asc())
        ).scalars().all()
    assert "device_provision" in actions
    assert "device_rotate_cert" in actions


def test_device_health_updates_with_telemetry_and_records_error_reason() -> None:
    client, session_factory = _build_testbed()
    shared_secret = "dev-secret-telemetry"
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        _seed_drone(db, drone_uid="DEV-DRN-002", shared_secret=shared_secret, platform_role=PlatformRole.recon)

    token = _login(client, "admin")
    auth_headers = {"Authorization": f"Bearer {token}"}
    provision = client.post(
        "/v2/devices/provision",
        headers=auth_headers,
        json={"device_id": "JETSON-002", "drone_uid": "DEV-DRN-002", "cert_fingerprint": "sha256:INIT"},
    )
    assert provision.status_code == 201

    payload = TelemetryPayload(
        lat=41.01,
        lon=28.98,
        alt_m=130.0,
        speed_mps=12.0,
        heading_deg=85.0,
        seq=1,
        source="unit-test",
    )
    raw = payload.model_dump_json().encode("utf-8")
    ok_headers = _signed_headers(
        drone_uid="DEV-DRN-002",
        shared_secret=shared_secret,
        nonce="n-1",
        raw_body=raw,
        device_id="JETSON-002",
    )
    ok_ingest = client.post("/v1/telemetry/ingest", headers={**ok_headers, "Content-Type": "application/json"}, content=payload.model_dump_json())
    assert ok_ingest.status_code == 202
    assert ok_ingest.json()["reason"] == "ok"
    assert ok_ingest.json()["platform_role"] == "recon"

    health_online = client.get("/v2/devices/JETSON-002/health", headers=auth_headers)
    assert health_online.status_code == 200
    assert health_online.json()["health"] == "online"
    assert health_online.json()["last_error_reason"] is None

    bad_headers = _signed_headers(
        drone_uid="DEV-DRN-002",
        shared_secret=shared_secret,
        nonce="n-2",
        raw_body=raw,
        bad_signature=True,
        device_id="JETSON-002",
    )
    bad_ingest = client.post("/v1/telemetry/ingest", headers={**bad_headers, "Content-Type": "application/json"}, content=payload.model_dump_json())
    assert bad_ingest.status_code == 400
    assert bad_ingest.json()["detail"] == "Signature validation failed"

    health_after_bad_sig = client.get("/v2/devices/JETSON-002/health", headers=auth_headers)
    assert health_after_bad_sig.status_code == 200
    assert health_after_bad_sig.json()["last_error_reason"] == "bad_signature"


def test_viewer_cannot_provision_device() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        _seed_user(db, username="viewer", role=UserRole.viewer)
        _seed_drone(db, drone_uid="DEV-DRN-003", shared_secret="dev-secret-003", platform_role=PlatformRole.interceptor)

    viewer_token = _login(client, "viewer")
    response = client.post(
        "/v2/devices/provision",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"device_id": "JETSON-003", "drone_uid": "DEV-DRN-003", "cert_fingerprint": "sha256:VIEWER"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"

    with session_factory() as db:
        item = db.execute(select(Device).where(Device.device_id == "JETSON-003")).scalar_one_or_none()
    assert item is None

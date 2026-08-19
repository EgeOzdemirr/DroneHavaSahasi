from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import (
    auth,
    demo,
    hostile_detections,
    intercept_tasks,
    operator_stations,
    recon,
    telemetry,
    tracks,
)
from app.db.base import Base
from app.db.models import Drone, DroneKey, FieldLayer, HostileDetection, InterceptTask, OperatorStation, TrackState, User
from app.db.session import get_db
from app.domain.enums import DroneStatus, FieldLayerType, HostileDetectionStatus, InterceptTaskStatus, KeyStatus, PlatformRole, SignatureAlgorithm, UserRole
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
    app.include_router(demo.router)
    app.include_router(telemetry.router)
    app.include_router(tracks.router)
    app.include_router(operator_stations.router)
    app.include_router(recon.router)
    app.include_router(hostile_detections.router)
    app.include_router(intercept_tasks.router)

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
    db.flush()
    return drone


def _login(client: TestClient, username: str, password: str = "Pass-For-Tests-123") -> str:
    response = client.post("/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _signed_headers(*, drone_uid: str, shared_secret: str, nonce: str, raw_body: bytes) -> dict[str, str]:
    ts_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    digest = body_sha256_hex(raw_body)
    canonical = canonical_signing_input(drone_uid, ts_ms, nonce, digest)
    signature = sign_hmac_hex(shared_secret, canonical)
    return {
        "X-Drone-Uid": drone_uid,
        "X-Ts": ts_ms,
        "X-Nonce": nonce,
        "X-Signature": signature,
        "X-Sig-Version": "hmac-sha256-v1",
    }


def _seed_detection_environment(session_factory: sessionmaker) -> dict[str, str]:
    with session_factory() as db:
        admin = _seed_user(db, username="admin", role=UserRole.admin)
        operator1 = _seed_user(db, username="operator1", role=UserRole.operator)
        operator2 = _seed_user(db, username="operator2", role=UserRole.operator)
        recon_drone = _seed_drone(db, drone_uid="RECON-001", shared_secret="recon-secret-001", platform_role=PlatformRole.recon)
        interceptor1 = _seed_drone(db, drone_uid="INT-001", shared_secret="int-secret-001", platform_role=PlatformRole.interceptor)
        interceptor2 = _seed_drone(db, drone_uid="INT-002", shared_secret="int-secret-002", platform_role=PlatformRole.interceptor)
        db.add(
            OperatorStation(
                user_id=operator1.id,
                name="OS-1",
                lat=41.0040,
                lon=29.0000,
                assigned_interceptor_drone_id=interceptor1.id,
                is_active=True,
            )
        )
        db.add(
            OperatorStation(
                user_id=operator2.id,
                name="OS-2",
                lat=41.0300,
                lon=29.0000,
                assigned_interceptor_drone_id=interceptor2.id,
                is_active=True,
            )
        )
        db.commit()
        return {
            "admin_id": admin.id,
            "recon_shared_secret": "recon-secret-001",
            "recon_uid": recon_drone.drone_uid,
        }


def _ingest_recon_track(client: TestClient, *, drone_uid: str, shared_secret: str) -> None:
    payload = TelemetryPayload(lat=41.0000, lon=29.0000, alt_m=100.0, speed_mps=20.0, heading_deg=0.0, seq=1, source="test")
    raw = payload.model_dump_json().encode("utf-8")
    headers = _signed_headers(
        drone_uid=drone_uid,
        shared_secret=shared_secret,
        nonce=f"n-track-{datetime.now(timezone.utc).timestamp()}",
        raw_body=raw,
    )
    response = client.post("/v1/telemetry/ingest", headers={**headers, "Content-Type": "application/json"}, content=payload.model_dump_json())
    assert response.status_code == 202


def test_signed_telemetry_updates_track_and_exposes_platform_role() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        _seed_drone(db, drone_uid="RECON-001", shared_secret="recon-secret-001", platform_role=PlatformRole.recon)
        db.commit()

    _ingest_recon_track(client, drone_uid="RECON-001", shared_secret="recon-secret-001")

    token = _login(client, "admin")
    tracks_resp = client.get("/v1/tracks", headers={"Authorization": f"Bearer {token}"})
    assert tracks_resp.status_code == 200
    body = tracks_resp.json()
    assert len(body) == 1
    assert body[0]["drone_uid"] == "RECON-001"
    assert body[0]["platform_role"] == "recon"
    assert body[0]["heading_deg"] == 0.0
    assert body[0]["speed_mps"] == 20.0


def test_recon_contact_creates_detection_and_assigns_nearest_operator_station() -> None:
    client, session_factory = _build_testbed()
    seed_info = _seed_detection_environment(session_factory)
    _ingest_recon_track(client, drone_uid=seed_info["recon_uid"], shared_secret=seed_info["recon_shared_secret"])

    admin_token = _login(client, "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post(
        "/v1/recon/contacts",
        headers=headers,
        json={
            "recon_drone_uid": seed_info["recon_uid"],
            "contact_id": "HST-001",
            "bearing_mil": 0.0,
            "range_m": 500.0,
            "elevation_mil": 0.0,
            "confidence": 82,
        },
    )
    assert response.status_code == 202
    detection = response.json()
    assert detection["status"] == "assigned"
    assert detection["assigned_operator_station_name"] == "OS-1"
    assert abs(detection["target_lon"] - 29.0) < 0.01
    assert detection["target_lat"] > 41.003

    tasks_resp = client.get("/v1/intercept-tasks", headers=headers)
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "pending"
    assert tasks[0]["operator_station_name"] == "OS-1"
    assert tasks[0]["interceptor_drone_uid"] == "INT-001"


def test_recon_contact_response_includes_field_layer_effects_for_detections_and_tasks() -> None:
    client, session_factory = _build_testbed()
    seed_info = _seed_detection_environment(session_factory)
    _ingest_recon_track(client, drone_uid=seed_info["recon_uid"], shared_secret=seed_info["recon_shared_secret"])

    restricted_geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [28.9980, 41.0020],
                [29.0020, 41.0020],
                [29.0020, 41.0070],
                [28.9980, 41.0070],
                [28.9980, 41.0020],
            ]
        ],
    }
    with session_factory() as db:
        db.add(
            FieldLayer(
                name="Test restricted area",
                layer_type=FieldLayerType.restricted_area,
                geometry=restricted_geometry,
                style={},
                is_active=True,
                created_by=seed_info["admin_id"],
            )
        )
        db.add(
            FieldLayer(
                name="Inactive perimeter",
                layer_type=FieldLayerType.base_perimeter,
                geometry=restricted_geometry,
                style={},
                is_active=False,
                created_by=seed_info["admin_id"],
            )
        )
        db.commit()

    admin_token = _login(client, "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post(
        "/v1/recon/contacts",
        headers=headers,
        json={
            "recon_drone_uid": seed_info["recon_uid"],
            "contact_id": "HST-LAYER-001",
            "bearing_mil": 0.0,
            "range_m": 500.0,
            "elevation_mil": 0.0,
            "confidence": 82,
        },
    )

    assert response.status_code == 202
    effects = response.json()["field_layer_effects"]
    assert len(effects) == 1
    assert effects[0]["layer_name"] == "Test restricted area"
    assert effects[0]["layer_type"] == "restricted_area"
    assert effects[0]["severity"] == "critical"

    tasks_resp = client.get("/v1/intercept-tasks", headers=headers)
    assert tasks_resp.status_code == 200
    task_effects = tasks_resp.json()[0]["field_layer_effects"]
    assert len(task_effects) == 1
    assert task_effects[0]["label"] == "Kısıtlı bölge teması"


def test_operator_can_accept_and_complete_task_flow() -> None:
    client, session_factory = _build_testbed()
    seed_info = _seed_detection_environment(session_factory)
    _ingest_recon_track(client, drone_uid=seed_info["recon_uid"], shared_secret=seed_info["recon_shared_secret"])

    admin_token = _login(client, "admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    create = client.post(
        "/v1/recon/contacts",
        headers=admin_headers,
        json={
            "recon_drone_uid": seed_info["recon_uid"],
            "contact_id": "HST-ACPT",
            "bearing_mil": 0.0,
            "range_m": 500.0,
            "confidence": 90,
        },
    )
    assert create.status_code == 202

    operator_token = _login(client, "operator1")
    operator_headers = {"Authorization": f"Bearer {operator_token}"}
    tasks_resp = client.get("/v1/intercept-tasks/me", headers=operator_headers)
    task_id = tasks_resp.json()[0]["id"]

    accept = client.post(f"/v1/intercept-tasks/{task_id}/accept", headers=operator_headers, json={"operator_note": "Yolda"})
    assert accept.status_code == 200
    assert accept.json()["status"] == "accepted"

    complete = client.post(f"/v1/intercept-tasks/{task_id}/complete", headers=operator_headers, json={"operator_note": "Imha tamam"})
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"

    detection_resp = client.get("/v1/hostile-detections", headers=admin_headers)
    detection = next(item for item in detection_resp.json() if item["contact_id"] == "HST-ACPT")
    assert detection["status"] == "resolved"


def test_rejecting_task_reopens_detection() -> None:
    client, session_factory = _build_testbed()
    seed_info = _seed_detection_environment(session_factory)
    _ingest_recon_track(client, drone_uid=seed_info["recon_uid"], shared_secret=seed_info["recon_shared_secret"])

    admin_token = _login(client, "admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    create = client.post(
        "/v1/recon/contacts",
        headers=admin_headers,
        json={
            "recon_drone_uid": seed_info["recon_uid"],
            "contact_id": "HST-RJCT",
            "bearing_mil": 0.0,
            "range_m": 500.0,
            "confidence": 70,
        },
    )
    assert create.status_code == 202

    operator_token = _login(client, "operator1")
    operator_headers = {"Authorization": f"Bearer {operator_token}"}
    tasks_resp = client.get("/v1/intercept-tasks/me", headers=operator_headers)
    task_id = next(item["id"] for item in tasks_resp.json() if item["contact_id"] == "HST-RJCT")

    reject = client.post(f"/v1/intercept-tasks/{task_id}/reject", headers=operator_headers, json={"operator_note": "Batarya kritik"})
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"

    detection_resp = client.get("/v1/hostile-detections", headers=admin_headers)
    detection = next(item for item in detection_resp.json() if item["contact_id"] == "HST-RJCT")
    assert detection["status"] == "open"
    assert detection["assigned_operator_station_id"] is None

    with session_factory() as db:
        task = db.execute(select(InterceptTask).where(InterceptTask.id == task_id)).scalar_one()
        assert task.status == InterceptTaskStatus.rejected
        detection_row = db.execute(select(HostileDetection).where(HostileDetection.contact_id == "HST-RJCT")).scalar_one()
        assert detection_row.status == HostileDetectionStatus.open


def test_demo_scenario_seed_creates_operator_tracks_and_credentials() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        db.commit()

    admin_token = _login(client, "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post(
        "/v1/demo/scenario",
        headers=headers,
        json={
            "recon_lat": 40.911,
            "recon_lon": 29.29,
            "recon_alt_m": 1200.0,
            "recon_heading_deg": 35.0,
            "stations": [
                {"name": "Tuzla Operator", "lat": 40.8255, "lon": 29.3095},
                {"name": "Pendik Operator", "lat": 40.8790, "lon": 29.2350},
                {"name": "Kartal Operator", "lat": 40.9055, "lon": 29.1850},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recon_drone_uid"] == "DEMO-RECON-01"
    assert len(body["operators"]) == 3
    assert body["operators"][0]["username"] == "demo_operator_1"

    stations = client.get("/v1/operator-stations", headers=headers)
    assert stations.status_code == 200
    assert len(stations.json()) == 3

    tracks_resp = client.get("/v1/tracks", headers=headers)
    assert tracks_resp.status_code == 200
    track_uids = {item["drone_uid"] for item in tracks_resp.json()}
    assert {"DEMO-RECON-01", "DEMO-INT-01", "DEMO-INT-02", "DEMO-INT-03"}.issubset(track_uids)


def test_demo_detection_can_create_multiple_map_targets() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        db.commit()

    admin_token = _login(client, "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    seed = client.post(
        "/v1/demo/scenario",
        headers=headers,
        json={
            "recon_lat": 40.911,
            "recon_lon": 29.29,
            "recon_alt_m": 1200.0,
            "recon_heading_deg": 35.0,
            "stations": [
                {"name": "Tuzla Operator", "lat": 40.8255, "lon": 29.3095},
                {"name": "Pendik Operator", "lat": 40.8790, "lon": 29.2350},
                {"name": "Kartal Operator", "lat": 40.9055, "lon": 29.1850},
            ],
        },
    )
    assert seed.status_code == 200
    with session_factory() as db:
        recon_track = db.execute(select(TrackState).where(TrackState.drone_uid == "DEMO-RECON-01")).scalar_one()
        recon_track.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.commit()

    contacts = [
        ("HST-DEMO-MAP-001", 40.8445, 29.3335),
        ("HST-DEMO-MAP-002", 40.8520, 29.3465),
        ("HST-DEMO-MAP-003", 40.8360, 29.3210),
    ]
    for contact_id, target_lat, target_lon in contacts:
        response = client.post(
            "/v1/demo/detections",
            headers=headers,
            json={
                "contact_id": contact_id,
                "target_lat": target_lat,
                "target_lon": target_lon,
                "target_alt_m": 350.0,
                "confidence": 88,
            },
        )
        assert response.status_code == 202
        assert response.json()["assigned_station_name"] == "Tuzla Operator"

    detections_resp = client.get("/v1/hostile-detections", headers=headers)
    assert detections_resp.status_code == 200
    detection_contacts = {item["contact_id"] for item in detections_resp.json()}
    assert {item[0] for item in contacts}.issubset(detection_contacts)

    tasks_resp = client.get("/v1/intercept-tasks", headers=headers)
    assert tasks_resp.status_code == 200
    task_contacts = {item["contact_id"] for item in tasks_resp.json()}
    assert {item[0] for item in contacts}.issubset(task_contacts)

    with session_factory() as db:
        stored = db.execute(select(HostileDetection).where(HostileDetection.contact_id.like("HST-DEMO-MAP-%"))).scalars().all()
        assert len(stored) == 3
        assert {item.status for item in stored} == {HostileDetectionStatus.assigned}


def test_admin_can_delete_hostile_detection_and_linked_tasks() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        db.commit()

    admin_token = _login(client, "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    seed = client.post(
        "/v1/demo/scenario",
        headers=headers,
        json={
            "recon_lat": 40.911,
            "recon_lon": 29.29,
            "recon_alt_m": 1200.0,
            "recon_heading_deg": 35.0,
            "stations": [
                {"name": "Tuzla Operator", "lat": 40.8255, "lon": 29.3095},
                {"name": "Pendik Operator", "lat": 40.8790, "lon": 29.2350},
                {"name": "Kartal Operator", "lat": 40.9055, "lon": 29.1850},
            ],
        },
    )
    assert seed.status_code == 200

    create = client.post(
        "/v1/demo/detections",
        headers=headers,
        json={
            "contact_id": "HST-DEMO-DELETE",
            "target_lat": 40.8445,
            "target_lon": 29.3335,
            "target_alt_m": 350.0,
            "confidence": 88,
        },
    )
    assert create.status_code == 202
    detection_id = create.json()["detection"]["id"]
    task_id = create.json()["assigned_task_id"]
    assert task_id is not None

    delete_resp = client.delete(f"/v1/hostile-detections/{detection_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp = client.get("/v1/hostile-detections", headers=headers)
    assert list_resp.status_code == 200
    assert all(item["id"] != detection_id for item in list_resp.json())
    tasks_resp = client.get("/v1/intercept-tasks", headers=headers)
    assert tasks_resp.status_code == 200
    assert all(item["id"] != task_id for item in tasks_resp.json())

    with session_factory() as db:
        assert db.get(HostileDetection, detection_id) is None
        assert db.get(InterceptTask, task_id) is None


def test_demo_detection_acceptance_simulates_and_auto_completes() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        db.commit()

    admin_token = _login(client, "admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    seed = client.post(
        "/v1/demo/scenario",
        headers=admin_headers,
        json={
            "recon_lat": 40.911,
            "recon_lon": 29.29,
            "recon_alt_m": 1200.0,
            "recon_heading_deg": 35.0,
            "stations": [
                {"name": "Tuzla Operator", "lat": 40.8255, "lon": 29.3095},
                {"name": "Pendik Operator", "lat": 40.8790, "lon": 29.2350},
                {"name": "Kartal Operator", "lat": 40.9055, "lon": 29.1850},
            ],
        },
    )
    assert seed.status_code == 200

    create = client.post(
        "/v1/demo/detections",
        headers=admin_headers,
        json={
            "contact_id": "HST-DEMO-ACPT",
            "target_lat": 40.8445,
            "target_lon": 29.3335,
            "target_alt_m": 350.0,
            "confidence": 88,
        },
    )
    assert create.status_code == 202
    assert create.json()["assigned_station_name"] == "Tuzla Operator"
    assert create.json()["detection"]["target_alt_m"] == 350.0

    operator_password = seed.json()["operators"][0]["password"]
    operator_token = _login(client, "demo_operator_1", operator_password)
    operator_headers = {"Authorization": f"Bearer {operator_token}"}
    tasks_resp = client.get("/v1/intercept-tasks/me", headers=operator_headers)
    assert tasks_resp.status_code == 200
    task_id = tasks_resp.json()[0]["id"]

    accept = client.post(f"/v1/intercept-tasks/{task_id}/accept", headers=operator_headers, json={"operator_note": "Demo kalkis"})
    assert accept.status_code == 200
    assert accept.json()["status"] == "accepted"

    tracks_resp = client.get("/v1/tracks", headers=admin_headers)
    assert tracks_resp.status_code == 200
    demo_track = next(item for item in tracks_resp.json() if item["drone_uid"] == "DEMO-INT-01")
    assert abs(demo_track["lat"] - 40.8255) < 0.01

    with session_factory() as db:
        task = db.execute(select(InterceptTask).where(InterceptTask.id == task_id)).scalar_one()
        task.accepted_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=10)
        db.commit()

    tasks_after = client.get("/v1/intercept-tasks", headers=admin_headers)
    assert tasks_after.status_code == 200
    updated_task = next(item for item in tasks_after.json() if item["id"] == task_id)
    assert updated_task["status"] == "completed"

    detections_after = client.get("/v1/hostile-detections", headers=admin_headers)
    detection = next(item for item in detections_after.json() if item["contact_id"] == "HST-DEMO-ACPT")
    assert detection["status"] == "resolved"


def test_demo_reset_deletes_only_demo_records() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        keep_user = _seed_user(db, username="operator_keep", role=UserRole.operator)
        keep_drone = _seed_drone(db, drone_uid="KEEP-INT-01", shared_secret="keep-secret", platform_role=PlatformRole.interceptor)
        db.add(
            OperatorStation(
                user_id=keep_user.id,
                name="KEEP-OS-1",
                lat=40.7,
                lon=29.1,
                assigned_interceptor_drone_id=keep_drone.id,
                is_active=True,
            )
        )
        db.commit()

    admin_token = _login(client, "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    seed = client.post(
        "/v1/demo/scenario",
        headers=headers,
        json={
            "recon_lat": 40.911,
            "recon_lon": 29.29,
            "recon_alt_m": 1200.0,
            "recon_heading_deg": 35.0,
            "stations": [
                {"name": "Tuzla Operatör", "lat": 40.8255, "lon": 29.3095},
                {"name": "Pendik Operatör", "lat": 40.8790, "lon": 29.2350},
                {"name": "Kartal Operatör", "lat": 40.9055, "lon": 29.1850},
            ],
        },
    )
    assert seed.status_code == 200
    create = client.post(
        "/v1/demo/detections",
        headers=headers,
        json={
            "contact_id": "HST-DEMO-RESET",
            "target_lat": 40.8445,
            "target_lon": 29.3335,
            "target_alt_m": 350.0,
            "confidence": 88,
        },
    )
    assert create.status_code == 202

    reset = client.post("/v1/demo/reset", headers=headers)
    assert reset.status_code == 200
    body = reset.json()
    assert body["deleted_drones"] == 4
    assert body["deleted_users"] == 3
    assert body["deleted_tasks"] >= 1
    assert body["deleted_detections"] >= 1

    with session_factory() as db:
        assert db.execute(select(Drone).where(Drone.drone_uid.like("DEMO-%"))).scalars().all() == []
        assert db.execute(select(User).where(User.username.like("demo_operator_%"))).scalars().all() == []
        assert db.execute(select(HostileDetection).where(HostileDetection.contact_id.like("HST-DEMO%"))).scalars().all() == []
        assert db.execute(select(Drone).where(Drone.drone_uid == "KEEP-INT-01")).scalar_one_or_none() is not None
        assert db.execute(select(User).where(User.username == "operator_keep")).scalar_one_or_none() is not None
        assert db.execute(select(OperatorStation).where(OperatorStation.name == "KEEP-OS-1")).scalar_one_or_none() is not None


def test_demo_endpoints_are_hidden_when_demo_mode_is_disabled(monkeypatch) -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        db.commit()

    monkeypatch.setattr(demo.settings, "demo_mode_enabled", False)
    admin_token = _login(client, "admin")
    response = client.post(
        "/v1/demo/scenario",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "recon_lat": 40.911,
            "recon_lon": 29.29,
            "recon_alt_m": 1200.0,
            "recon_heading_deg": 35.0,
            "stations": [{"name": "Tuzla Operatör", "lat": 40.8255, "lon": 29.3095}],
        },
    )
    assert response.status_code == 404

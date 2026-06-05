from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import air_traffic, auth
from app.db.base import Base
from app.db.models import User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.schemas.models import OpenSkyAircraftResponse
from app.security.auth import hash_password


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
    app.include_router(air_traffic.router)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_factory


def _seed_user(db: Session, *, username: str, role: UserRole) -> None:
    db.add(
        User(
            username=username,
            password_hash=hash_password("Pass-For-Tests-123"),
            role=role,
            is_active=True,
            must_change_password=False,
        )
    )


def _login(client: TestClient, username: str) -> str:
    response = client.post("/v1/auth/login", json={"username": username, "password": "Pass-For-Tests-123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_opensky_air_traffic_endpoint_allows_read_roles(monkeypatch) -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        _seed_user(db, username="operator", role=UserRole.operator)
        _seed_user(db, username="viewer", role=UserRole.viewer)
        db.commit()

    monkeypatch.setattr(air_traffic.settings, "opensky_enabled", True)
    monkeypatch.setattr(
        air_traffic,
        "fetch_opensky_aircraft",
        lambda _settings: [
            OpenSkyAircraftResponse(
                icao24="4baa01",
                callsign="THY123",
                origin_country="Turkey",
                lat=40.883,
                lon=29.302,
                baro_altitude_m=3400.5,
                geo_altitude_m=3450.0,
                velocity_mps=215.3,
                true_track_deg=92.0,
                vertical_rate_mps=-1.2,
                on_ground=False,
                last_contact=datetime(2024, 3, 9, tzinfo=timezone.utc),
                category=3,
            )
        ],
    )

    for username in ["admin", "operator", "viewer"]:
        token = _login(client, username)
        response = client.get("/v1/air-traffic/opensky", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()[0]["icao24"] == "4baa01"
        assert response.json()[0]["callsign"] == "THY123"


def test_opensky_air_traffic_endpoint_is_hidden_when_disabled(monkeypatch) -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        db.commit()

    monkeypatch.setattr(air_traffic.settings, "opensky_enabled", False)
    token = _login(client, "admin")
    response = client.get("/v1/air-traffic/opensky", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404

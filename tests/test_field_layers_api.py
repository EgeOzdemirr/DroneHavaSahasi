from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import auth, field_layers
from app.db.base import Base
from app.db.models import User
from app.db.session import get_db
from app.domain.enums import UserRole
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
    app.include_router(field_layers.router)

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


def _login(client: TestClient, username: str) -> dict[str, str]:
    response = client.post("/v1/auth/login", json={"username": username, "password": "Pass-For-Tests-123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _polygon() -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [29.2000, 40.8000],
                [29.3500, 40.8000],
                [29.3500, 40.9100],
                [29.2000, 40.9100],
                [29.2000, 40.8000],
            ]
        ],
    }


def test_admin_can_create_patch_list_and_delete_field_layer() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        db.commit()
    headers = _login(client, "admin")

    create = client.post(
        "/v1/field-layers",
        headers=headers,
        json={
            "name": "Tuzla us cevresi",
            "layer_type": "base_perimeter",
            "geometry": _polygon(),
            "style": {"color": "#38d39f"},
            "is_active": True,
        },
    )
    assert create.status_code == 201
    layer = create.json()
    assert layer["name"] == "Tuzla us cevresi"
    assert layer["layer_type"] == "base_perimeter"
    assert layer["created_by"]

    listing = client.get("/v1/field-layers", headers=headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [layer["id"]]

    patch = client.patch(
        f"/v1/field-layers/{layer['id']}",
        headers=headers,
        json={"name": "Guvenli koridor", "layer_type": "safe_corridor", "is_active": False},
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "Guvenli koridor"
    assert patch.json()["is_active"] is False

    active_listing = client.get("/v1/field-layers", headers=headers)
    assert active_listing.status_code == 200
    assert active_listing.json() == []

    delete = client.delete(f"/v1/field-layers/{layer['id']}", headers=headers)
    assert delete.status_code == 204


def test_operator_and_viewer_can_only_read_field_layers() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        _seed_user(db, username="operator", role=UserRole.operator)
        _seed_user(db, username="viewer", role=UserRole.viewer)
        db.commit()
    admin_headers = _login(client, "admin")
    operator_headers = _login(client, "operator")
    viewer_headers = _login(client, "viewer")

    create = client.post(
        "/v1/field-layers",
        headers=admin_headers,
        json={"name": "Devriye bolgesi", "layer_type": "patrol_area", "geometry": _polygon()},
    )
    assert create.status_code == 201

    assert client.get("/v1/field-layers", headers=operator_headers).status_code == 200
    assert client.get("/v1/field-layers", headers=viewer_headers).status_code == 200
    assert client.post(
        "/v1/field-layers",
        headers=operator_headers,
        json={"name": "Yetkisiz", "layer_type": "custom", "geometry": _polygon()},
    ).status_code == 403
    assert client.delete(f"/v1/field-layers/{create.json()['id']}", headers=viewer_headers).status_code == 403


def test_invalid_polygon_is_rejected() -> None:
    client, session_factory = _build_testbed()
    with session_factory() as db:
        _seed_user(db, username="admin", role=UserRole.admin)
        db.commit()
    headers = _login(client, "admin")

    response = client.post(
        "/v1/field-layers",
        headers=headers,
        json={
            "name": "Bozuk alan",
            "layer_type": "custom",
            "geometry": {"type": "Polygon", "coordinates": [[[29.2, 40.8], [29.3, 40.8], [29.2, 40.9]]]},
        },
    )
    assert response.status_code == 422

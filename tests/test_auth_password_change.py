from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import require_roles
from app.api.routers import auth
from app.db.base import Base
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.security.auth import decode_access_token, hash_password


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

    @app.get("/v1/protected")
    def protected(_user: User = Depends(require_roles(UserRole.admin))) -> dict[str, bool]:
        return {"ok": True}

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    return client, session_factory


def _create_user(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        user = User(
            username="admin",
            password_hash=hash_password("admin123"),
            role=UserRole.admin,
            is_active=True,
            must_change_password=True,
        )
        db.add(user)
        db.commit()


def _login(client: TestClient) -> dict:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    return response.json()


def test_login_requires_password_change_and_claim() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory)

    payload = _login(client)
    assert payload["password_change_required"] is True

    claims = decode_access_token(payload["access_token"])
    assert claims is not None
    assert claims["pwd_reset_required"] is True


def test_protected_endpoint_blocked_until_password_changes() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory)

    payload = _login(client)
    token = payload["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    blocked = client.get("/v1/protected", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "password_change_required"

    change = client.post(
        "/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "admin123",
            "new_password": "AdminPass-AfterReset-001",
        },
    )
    assert change.status_code == 200
    assert change.json()["password_change_required"] is False

    allowed = client.get("/v1/protected", headers=headers)
    assert allowed.status_code == 200
    assert allowed.json() == {"ok": True}


def test_change_password_validation_and_audit() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory)
    token = _login(client)["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bad_current = client.post(
        "/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "wrong",
            "new_password": "AdminPass-AfterReset-001",
        },
    )
    assert bad_current.status_code == 400
    assert bad_current.json()["detail"] == "current_password_invalid"

    too_short = client.post(
        "/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "admin123",
            "new_password": "short",
        },
    )
    assert too_short.status_code == 400
    assert too_short.json()["detail"] == "new_password_min_length_12"

    with session_factory() as db:
        actions = db.execute(
            select(AuditLog.action).where(AuditLog.actor_username == "admin").order_by(AuditLog.created_at.asc())
        ).scalars().all()
    assert "password_change_failed_bad_current" in actions
    assert "password_change_failed_policy" in actions

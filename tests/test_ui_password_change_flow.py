from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import ui
from app.config import get_settings
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
    app.include_router(ui.router)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_factory


def _create_user(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        db.add(
            User(
                username="admin",
                password_hash=hash_password("admin123"),
                role=UserRole.admin,
                is_active=True,
                must_change_password=True,
            )
        )
        db.commit()


def test_ui_redirects_to_change_password_and_unlocks_after_change() -> None:
    client, session_factory = _build_testbed()
    _create_user(session_factory)
    settings = get_settings()

    login_page = client.get("/ui/login")
    assert login_page.status_code == 200
    csrf = client.cookies.get(settings.csrf_cookie_name)

    login_submit = client.post(
        "/ui/login",
        data={"username": "admin", "password": "admin123", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert login_submit.status_code == 302
    assert login_submit.headers["location"] == "/ui/change-password"

    tactical_blocked = client.get("/ui/tactical", follow_redirects=False)
    assert tactical_blocked.status_code == 302
    assert tactical_blocked.headers["location"] == "/ui/change-password"

    change_page = client.get("/ui/change-password")
    assert change_page.status_code == 200

    csrf_change = client.cookies.get(settings.csrf_cookie_name)
    submit_change = client.post(
        "/ui/change-password",
        data={
            "current_password": "admin123",
            "new_password": "AdminPass-AfterReset-001",
            "confirm_password": "AdminPass-AfterReset-001",
            "csrf_token": csrf_change,
        },
        follow_redirects=False,
    )
    assert submit_change.status_code == 302
    assert submit_change.headers["location"] == "/ui/control-center"

    tactical_ok = client.get("/ui/tactical", follow_redirects=False)
    assert tactical_ok.status_code == 302
    assert tactical_ok.headers["location"] == "/ui/control-center"

    control_center = client.get("/ui/control-center")
    assert control_center.status_code == 200

    with session_factory() as db:
        user = db.execute(select(User).where(User.username == "admin")).scalar_one()
        assert user.must_change_password is False
        assert user.password_changed_at is not None

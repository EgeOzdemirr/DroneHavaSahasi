from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import auth
from app.db.base import Base
from app.db.models import User
from app.db.session import get_db
from app.domain.enums import UserRole
from app.security.auth import hash_password
from app.services import login_rate_limit


def _build(monkeypatch) -> tuple[TestClient, str]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with session_factory() as db:
        db.add(
            User(
                username="admin",
                password_hash=hash_password("dogru-parola-2026"),
                role=UserRole.admin,
                is_active=True,
                must_change_password=False,
            )
        )
        db.commit()

    # Her test icin taze, dusuk esikli, Redis'siz limiter.
    limiter = login_rate_limit.LoginRateLimiter.__new__(login_rate_limit.LoginRateLimiter)
    limiter.max_attempts = 3
    limiter.window_seconds = 300
    import threading
    limiter._lock = threading.Lock()
    limiter._memory = {}
    limiter._redis = None
    monkeypatch.setattr(login_rate_limit, "login_rate_limiter", limiter)
    monkeypatch.setattr(auth, "login_rate_limiter", limiter)

    app = FastAPI()
    app.include_router(auth.router)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), "dogru-parola-2026"


def _login(client: TestClient, password: str):
    return client.post("/v1/auth/login", json={"username": "admin", "password": password})


def test_blocks_after_max_failed_attempts(monkeypatch) -> None:
    client, good = _build(monkeypatch)

    # 3 basarisiz deneme (esik) -> hepsi 401
    for _ in range(3):
        assert _login(client, "yanlis").status_code == 401

    # 4. deneme, dogru sifre olsa bile 429 (kilit)
    blocked = _login(client, good)
    assert blocked.status_code == 429


def test_successful_login_resets_the_counter(monkeypatch) -> None:
    client, good = _build(monkeypatch)

    # esigin altinda 2 basarisiz
    assert _login(client, "yanlis").status_code == 401
    assert _login(client, "yanlis").status_code == 401
    # dogru giris sayaci sifirlar
    assert _login(client, good).status_code == 200
    # tekrar bastan sayar: 2 basarisiz hala engellenmez
    assert _login(client, "yanlis").status_code == 401
    assert _login(client, "yanlis").status_code == 401
    assert _login(client, good).status_code == 200

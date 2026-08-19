from cryptography.fernet import Fernet
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.db.models import User
from app.domain.enums import UserRole
from app.security.auth import hash_password, verify_password
from app.services import bootstrap


VALID_MASTER_KEY = Fernet.generate_key().decode()  # test icin gecici anahtar; repoda sabit deger yok
VIEWER_PASSWORD = "gozlemci-demo-2026"


def _build_session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "MASTER_KEY": VALID_MASTER_KEY,
        "BOOTSTRAP_ADMIN_USERNAME": "komutan",
    }
    values.update(overrides)
    return Settings(**values)


def _run(monkeypatch: pytest.MonkeyPatch, settings: Settings, session_factory: sessionmaker) -> None:
    monkeypatch.setattr(bootstrap, "get_settings", lambda: settings)
    with session_factory() as db:
        bootstrap.ensure_bootstrap_viewer(db)


def _fetch(session_factory: sessionmaker, username: str) -> User | None:
    with session_factory() as db:
        return db.execute(select(User).where(User.username == username)).scalar_one_or_none()


def test_creates_read_only_viewer_account(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = _build_session_factory()
    settings = _settings(
        BOOTSTRAP_VIEWER_USERNAME="gozlemci",
        BOOTSTRAP_VIEWER_PASSWORD=VIEWER_PASSWORD,
    )

    _run(monkeypatch, settings, session_factory)

    viewer = _fetch(session_factory, "gozlemci")
    assert viewer is not None
    assert viewer.role is UserRole.viewer
    assert viewer.is_active is True
    # Paylasilan demo hesabi kilitlenemesin diye sifre degistirme zorunlulugu yok.
    assert viewer.must_change_password is False
    assert verify_password(VIEWER_PASSWORD, viewer.password_hash)


def test_skips_when_viewer_credentials_are_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = _build_session_factory()

    _run(monkeypatch, _settings(), session_factory)
    _run(monkeypatch, _settings(BOOTSTRAP_VIEWER_USERNAME="gozlemci"), session_factory)
    _run(monkeypatch, _settings(BOOTSTRAP_VIEWER_PASSWORD=VIEWER_PASSWORD), session_factory)

    with session_factory() as db:
        assert db.execute(select(User)).scalars().all() == []


def test_never_overwrites_the_admin_account(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = _build_session_factory()
    with session_factory() as db:
        db.add(
            User(
                username="komutan",
                password_hash=hash_password("admin-parolasi-2026"),
                role=UserRole.admin,
                is_active=True,
                must_change_password=False,
            )
        )
        db.commit()

    settings = _settings(
        BOOTSTRAP_VIEWER_USERNAME="komutan",
        BOOTSTRAP_VIEWER_PASSWORD=VIEWER_PASSWORD,
    )
    _run(monkeypatch, settings, session_factory)

    admin = _fetch(session_factory, "komutan")
    assert admin is not None
    assert admin.role is UserRole.admin
    assert verify_password("admin-parolasi-2026", admin.password_hash)


def test_restores_a_tampered_viewer_account_on_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = _build_session_factory()
    with session_factory() as db:
        db.add(
            User(
                username="gozlemci",
                password_hash=hash_password("ele-gecirilmis-parola"),
                role=UserRole.admin,
                is_active=False,
                must_change_password=True,
            )
        )
        db.commit()

    settings = _settings(
        BOOTSTRAP_VIEWER_USERNAME="gozlemci",
        BOOTSTRAP_VIEWER_PASSWORD=VIEWER_PASSWORD,
    )
    _run(monkeypatch, settings, session_factory)

    viewer = _fetch(session_factory, "gozlemci")
    assert viewer is not None
    assert viewer.role is UserRole.viewer
    assert viewer.is_active is True
    assert viewer.must_change_password is False
    assert verify_password(VIEWER_PASSWORD, viewer.password_hash)
    assert not verify_password("ele-gecirilmis-parola", viewer.password_hash)


def test_prod_rejects_weak_viewer_password() -> None:
    with pytest.raises(ValidationError, match="BOOTSTRAP_VIEWER_PASSWORD is too weak for prod"):
        Settings(
            _env_file=None,
            ENVIRONMENT="prod",
            MASTER_KEY=VALID_MASTER_KEY,
            JWT_SECRET_KEY="this-is-a-strong-jwt-secret-value-12345",
            BOOTSTRAP_ADMIN_PASSWORD="strong-admin-password",
            BOOTSTRAP_VIEWER_USERNAME="gozlemci",
            BOOTSTRAP_VIEWER_PASSWORD="kisa",
            SECURE_COOKIES=True,
            CORS_ORIGINS=["https://ops.local"],
        )


def test_prod_rejects_viewer_username_equal_to_admin() -> None:
    with pytest.raises(ValidationError, match="BOOTSTRAP_VIEWER_USERNAME cannot equal"):
        Settings(
            _env_file=None,
            ENVIRONMENT="prod",
            MASTER_KEY=VALID_MASTER_KEY,
            JWT_SECRET_KEY="this-is-a-strong-jwt-secret-value-12345",
            BOOTSTRAP_ADMIN_USERNAME="komutan",
            BOOTSTRAP_ADMIN_PASSWORD="strong-admin-password",
            BOOTSTRAP_VIEWER_USERNAME="komutan",
            BOOTSTRAP_VIEWER_PASSWORD="gozlemci-demo-2026",
            SECURE_COOKIES=True,
            CORS_ORIGINS=["https://ops.local"],
        )

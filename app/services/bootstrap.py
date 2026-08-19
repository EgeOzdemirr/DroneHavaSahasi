from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.domain.enums import UserRole
from app.security.auth import hash_password


def ensure_bootstrap_admin(db: Session) -> None:
    settings = get_settings()
    stmt = select(User).where(User.username == settings.bootstrap_admin_username)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        return

    user = User(
        username=settings.bootstrap_admin_username,
        password_hash=hash_password(settings.bootstrap_admin_password),
        role=UserRole.admin,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.commit()


def ensure_bootstrap_viewer(db: Session) -> None:
    """Salt-okunur demo hesabini ortam degiskenlerinden olusturur.

    Hesap her aciliste ortam degerleriyle eslenir: rolu viewer'a sabitlenir,
    sifresi yeniden yazilir ve sifre degistirme zorunlulugu kaldirilir. Boylece
    paylasilan demo hesabini biri degistirse bile sonraki yeniden baslatmada
    eski haline doner ve hesap kilitlenemez.
    """
    settings = get_settings()
    username = settings.bootstrap_viewer_username.strip()
    password = settings.bootstrap_viewer_password.strip()
    if not username or not password:
        return
    if username == settings.bootstrap_admin_username.strip():
        return

    password_hash = hash_password(password)
    stmt = select(User).where(User.username == username)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        existing.role = UserRole.viewer
        existing.is_active = True
        existing.must_change_password = False
        existing.password_hash = password_hash
        db.add(existing)
    else:
        db.add(
            User(
                username=username,
                password_hash=password_hash,
                role=UserRole.viewer,
                is_active=True,
                must_change_password=False,
            )
        )
    db.commit()

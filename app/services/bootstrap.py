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

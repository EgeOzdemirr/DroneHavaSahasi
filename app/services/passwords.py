from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import User
from app.security.auth import hash_password, verify_password

MIN_PASSWORD_LENGTH = 12


def password_change_violation(user: User, *, current_password: str, new_password: str) -> str | None:
    if not verify_password(current_password, user.password_hash):
        return "bad_current_password"
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return "min_length"
    if verify_password(new_password, user.password_hash):
        return "same_as_current"
    return None


def apply_password_change(user: User, *, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)

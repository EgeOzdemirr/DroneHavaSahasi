import secrets
from hmac import compare_digest


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(cookie_value: str | None, provided_value: str | None) -> bool:
    if not cookie_value or not provided_value:
        return False
    return compare_digest(cookie_value, provided_value)


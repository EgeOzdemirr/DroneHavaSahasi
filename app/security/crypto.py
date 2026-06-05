from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    return Fernet(settings.master_key.encode("utf-8"))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(secret_enc: str) -> str:
    return _fernet().decrypt(secret_enc.encode("utf-8")).decode("utf-8")


import pytest
from pydantic import ValidationError

from app.config import Settings
from bridge.config import BridgeSettings


VALID_MASTER_KEY = "***REMOVED***"


def test_app_settings_rejects_weak_prod_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY is too weak for prod"):
        Settings(
            _env_file=None,
            ENVIRONMENT="prod",
            MASTER_KEY=VALID_MASTER_KEY,
            JWT_SECRET_KEY="change-me",
            BOOTSTRAP_ADMIN_PASSWORD="admin123456789",
            SECURE_COOKIES=True,
            CORS_ORIGINS=["https://ops.local"],
        )


def test_app_settings_rejects_prod_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS cannot contain '\\*' in prod"):
        Settings(
            _env_file=None,
            ENVIRONMENT="prod",
            MASTER_KEY=VALID_MASTER_KEY,
            JWT_SECRET_KEY="this-is-a-strong-jwt-secret-value-12345",
            BOOTSTRAP_ADMIN_PASSWORD="strong-admin-password",
            SECURE_COOKIES=True,
            CORS_ORIGINS=["*"],
        )


def test_app_settings_accepts_strong_prod_values() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="prod",
        MASTER_KEY=VALID_MASTER_KEY,
        JWT_SECRET_KEY="this-is-a-strong-jwt-secret-value-12345",
        BOOTSTRAP_ADMIN_PASSWORD="strong-admin-password",
        SECURE_COOKIES=True,
        CORS_ORIGINS=["https://ops.local"],
    )
    assert settings.environment == "prod"


def test_bridge_settings_rejects_weak_prod_source_token() -> None:
    with pytest.raises(ValidationError, match="BRIDGE_SOURCE_TOKEN is too weak for prod"):
        BridgeSettings(
            _env_file=None,
            ENVIRONMENT="prod",
            BRIDGE_SOURCE_TOKEN="change-me-bridge-token",
        )


def test_bridge_settings_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValidationError, match="BRIDGE_FORWARD_TIMEOUT_SECONDS must be > 0"):
        BridgeSettings(
            _env_file=None,
            ENVIRONMENT="dev",
            BRIDGE_SOURCE_TOKEN="dev-token-that-is-long-enough-123",
            BRIDGE_FORWARD_TIMEOUT_SECONDS=0,
        )


def test_bridge_settings_accepts_strong_prod_values() -> None:
    settings = BridgeSettings(
        _env_file=None,
        ENVIRONMENT="prod",
        BRIDGE_SOURCE_TOKEN="strong-bridge-token-value-0123456789",
        BRIDGE_FORWARD_TIMEOUT_SECONDS=2,
        BRIDGE_RETRY_MAX_ATTEMPTS=5,
        BRIDGE_RETRY_BACKOFF_SECONDS=1,
        BRIDGE_QUEUE_MAX=10000,
    )
    assert settings.environment == "prod"

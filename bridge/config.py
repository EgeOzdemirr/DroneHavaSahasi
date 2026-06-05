from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BridgeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Friend Drone Bridge", alias="BRIDGE_APP_NAME")
    environment: Literal["dev", "test", "prod"] = Field(default="dev", alias="ENVIRONMENT")

    bridge_port: int = Field(default=8100, alias="BRIDGE_PORT")
    bridge_source_token: str = Field(default="change-me-bridge-token", alias="BRIDGE_SOURCE_TOKEN")
    bridge_api_ingest_url: str = Field(default="http://localhost:8000/v1/telemetry/ingest", alias="BRIDGE_API_INGEST_URL")
    bridge_forward_timeout_seconds: float = Field(default=2.0, alias="BRIDGE_FORWARD_TIMEOUT_SECONDS")
    bridge_retry_max_attempts: int = Field(default=5, alias="BRIDGE_RETRY_MAX_ATTEMPTS")
    bridge_retry_backoff_seconds: float = Field(default=1.0, alias="BRIDGE_RETRY_BACKOFF_SECONDS")
    bridge_queue_key: str = Field(default="bridge:telemetry:retry", alias="BRIDGE_QUEUE_KEY")
    bridge_dlq_key: str = Field(default="bridge:telemetry:dlq", alias="BRIDGE_DLQ_KEY")
    bridge_queue_max: int = Field(default=10_000, alias="BRIDGE_QUEUE_MAX")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    @model_validator(mode="after")
    def validate_security_and_bounds(self) -> "BridgeSettings":
        if self.bridge_forward_timeout_seconds <= 0:
            raise ValueError("BRIDGE_FORWARD_TIMEOUT_SECONDS must be > 0.")
        if self.bridge_retry_max_attempts < 1:
            raise ValueError("BRIDGE_RETRY_MAX_ATTEMPTS must be >= 1.")
        if self.bridge_retry_backoff_seconds < 0:
            raise ValueError("BRIDGE_RETRY_BACKOFF_SECONDS must be >= 0.")
        if self.bridge_queue_max < 1:
            raise ValueError("BRIDGE_QUEUE_MAX must be >= 1.")

        if self.environment == "prod":
            weak_tokens = {
                "change-me-bridge-token",
                "change-me",
                "changeme",
                "token",
                "default",
            }
            lowered_token = self.bridge_source_token.strip().lower()
            if lowered_token in weak_tokens or len(self.bridge_source_token.strip()) < 24:
                raise ValueError("BRIDGE_SOURCE_TOKEN is too weak for prod.")

        return self


@lru_cache(maxsize=1)
def get_bridge_settings() -> BridgeSettings:
    return BridgeSettings()

from functools import lru_cache
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Hava Sahasi Kontrol Merkezi", alias="APP_NAME")
    environment: Literal["dev", "test", "prod"] = Field(default="dev", alias="ENVIRONMENT")

    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/friend_drone",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=120, alias="JWT_EXPIRE_MINUTES")
    access_cookie_name: str = Field(default="fd_access_token", alias="ACCESS_COOKIE_NAME")
    csrf_cookie_name: str = Field(default="fd_csrf_token", alias="CSRF_COOKIE_NAME")
    secure_cookies: bool = Field(default=False, alias="SECURE_COOKIES")
    session_max_age_seconds: int = Field(default=7200, alias="SESSION_MAX_AGE_SECONDS")

    master_key: str = Field(alias="MASTER_KEY")

    bootstrap_admin_username: str = Field(default="admin", alias="BOOTSTRAP_ADMIN_USERNAME")
    bootstrap_admin_password: str = Field(default="admin123", alias="BOOTSTRAP_ADMIN_PASSWORD")

    # Salt-okunur demo hesabi. Ikisi de doluysa acilista olusturulur.
    bootstrap_viewer_username: str = Field(default="", alias="BOOTSTRAP_VIEWER_USERNAME")
    bootstrap_viewer_password: str = Field(default="", alias="BOOTSTRAP_VIEWER_PASSWORD")

    # Giris denemesi hiz siniri (brute-force korumasi). Bir istemci penceresi
    # icinde en fazla login_max_attempts basarisiz denemeye izin verilir; asilirsa
    # pencere dolana kadar 429 doner. Basarili giris sayaci sifirlar.
    login_max_attempts: int = Field(default=10, alias="LOGIN_MAX_ATTEMPTS")
    login_window_seconds: int = Field(default=300, alias="LOGIN_WINDOW_SECONDS")

    telemetry_allowed_skew_seconds: int = Field(default=30, alias="TELEMETRY_ALLOWED_SKEW_SECONDS")
    nonce_ttl_seconds: int = Field(default=120, alias="NONCE_TTL_SECONDS")
    retention_days: int = Field(default=30, alias="RETENTION_DAYS")
    link_lost_seconds: int = Field(default=10, alias="LINK_LOST_SECONDS")
    recon_track_max_age_seconds: int = Field(default=30, alias="RECON_TRACK_MAX_AGE_SECONDS")
    demo_mode_enabled: bool = Field(default=True, alias="DEMO_MODE_ENABLED")
    demo_interceptor_speed_mps: float = Field(default=95.0, alias="DEMO_INTERCEPTOR_SPEED_MPS")
    demo_interceptor_min_duration_seconds: int = Field(default=25, alias="DEMO_INTERCEPTOR_MIN_DURATION_SECONDS")
    # Bos birakilirsa senaryo yuklemede sureç basina rastgele bir sifre uretilir
    # ve seed yanitinda dondurulur; boylece repoda sabit bir demo sifresi tutulmaz.
    demo_operator_password: str = Field(default="", alias="DEMO_OPERATOR_PASSWORD")
    map_provider: Literal["openfreemap", "offline"] = Field(default="openfreemap", alias="MAP_PROVIDER")
    map_label_language: str = Field(default="tr", alias="MAP_LABEL_LANGUAGE")
    map_hidden_labels: str = Field(
        default="Kürdistan Bölgesel Yönetimi,Kürdistan,Kurdistan Region,Kurdistan Regional Government,Kurdistan",
        alias="MAP_HIDDEN_LABELS",
    )
    map_style_url: str = Field(default="https://tiles.openfreemap.org/styles/liberty", alias="MAP_STYLE_URL")
    map_home_lat: float = Field(default=39.0, alias="MAP_HOME_LAT")
    map_home_lon: float = Field(default=35.2, alias="MAP_HOME_LON")
    map_home_zoom: float = Field(default=5.4, alias="MAP_HOME_ZOOM")
    map_min_zoom: int = Field(default=2, alias="MAP_MIN_ZOOM")
    map_max_zoom: int = Field(default=19, alias="MAP_MAX_ZOOM")
    maplibre_css_url: str = Field(
        default="https://unpkg.com/maplibre-gl/dist/maplibre-gl.css",
        alias="MAPLIBRE_CSS_URL",
    )
    maplibre_js_url: str = Field(
        default="https://unpkg.com/maplibre-gl/dist/maplibre-gl.js",
        alias="MAPLIBRE_JS_URL",
    )
    maplibre_leaflet_js_url: str = Field(
        default="https://unpkg.com/@maplibre/maplibre-gl-leaflet/leaflet-maplibre-gl.js",
        alias="MAPLIBRE_LEAFLET_JS_URL",
    )
    opensky_enabled: bool = Field(default=True, alias="OPENSKY_ENABLED")
    opensky_bbox: str = Field(default="34.0,18.0,45.5,45.5", alias="OPENSKY_BBOX")
    opensky_base_url: str = Field(default="https://opensky-network.org/api", alias="OPENSKY_BASE_URL")
    opensky_cache_ttl_seconds: int = Field(default=30, alias="OPENSKY_CACHE_TTL_SECONDS")
    opensky_timeout_seconds: float = Field(default=6.0, alias="OPENSKY_TIMEOUT_SECONDS")
    opensky_client_id: str = Field(default="", alias="OPENSKY_CLIENT_ID")
    opensky_client_secret: str = Field(default="", alias="OPENSKY_CLIENT_SECRET")

    cors_origins: list[str] = Field(default=["*"], alias="CORS_ORIGINS")

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment != "prod":
            return self

        weak_values = {
            "change-me",
            "change-me-for-production",
            "changeme",
            "secret",
            "default",
        }
        lowered_jwt_secret = self.jwt_secret_key.strip().lower()
        if lowered_jwt_secret in weak_values or len(self.jwt_secret_key.strip()) < 32:
            raise ValueError("JWT_SECRET_KEY is too weak for prod. Use at least 32 chars and avoid default values.")

        try:
            Fernet(self.master_key.encode("utf-8"))
        except (ValueError, TypeError):
            raise ValueError("MASTER_KEY is invalid. Provide a valid Fernet key for prod.")

        if self.bootstrap_admin_password == "admin123" or len(self.bootstrap_admin_password) < 12:
            raise ValueError("BOOTSTRAP_ADMIN_PASSWORD is too weak for prod.")

        if self.bootstrap_viewer_username.strip():
            if len(self.bootstrap_viewer_password.strip()) < 12:
                raise ValueError("BOOTSTRAP_VIEWER_PASSWORD is too weak for prod.")
            if self.bootstrap_viewer_username.strip() == self.bootstrap_admin_username.strip():
                raise ValueError("BOOTSTRAP_VIEWER_USERNAME cannot equal BOOTSTRAP_ADMIN_USERNAME.")

        if not self.secure_cookies:
            raise ValueError("SECURE_COOKIES must be true in prod.")

        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS cannot contain '*' in prod.")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

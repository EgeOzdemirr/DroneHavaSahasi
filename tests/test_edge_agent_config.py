import pytest

from edge_agent.config import parse_settings


def test_parse_settings_rejects_log_every_zero():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--shared-secret",
        "secret-1",
        "--log-every",
        "0",
    ]
    with pytest.raises(SystemExit, match="--log-every must be >= 1"):
        parse_settings(argv)


def test_parse_settings_accepts_log_every_positive():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--shared-secret",
        "secret-1",
        "--log-every",
        "5",
    ]
    settings = parse_settings(argv)
    assert settings.log_every == 5


def test_parse_settings_rejects_negative_retry_backoff_seconds():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--shared-secret",
        "secret-1",
        "--retry-backoff-seconds",
        "-1",
    ]
    with pytest.raises(SystemExit, match="--retry-backoff-seconds must be >= 0"):
        parse_settings(argv)


def test_parse_settings_rejects_negative_retry_backoff_max_seconds():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--shared-secret",
        "secret-1",
        "--retry-backoff-max-seconds",
        "-5",
    ]
    with pytest.raises(SystemExit, match="--retry-backoff-max-seconds must be >= 0"):
        parse_settings(argv)


def test_parse_settings_rejects_retry_backoff_max_less_than_base():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--shared-secret",
        "secret-1",
        "--retry-backoff-seconds",
        "10",
        "--retry-backoff-max-seconds",
        "5",
    ]
    with pytest.raises(SystemExit, match="--retry-backoff-max-seconds must be >= --retry-backoff-seconds"):
        parse_settings(argv)


def test_parse_settings_rejects_partial_mtls_client_pair():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--shared-secret",
        "secret-1",
        "--tls-client-cert-file",
        "client.crt",
    ]
    with pytest.raises(SystemExit, match="--tls-client-cert-file and --tls-client-key-file must be provided together"):
        parse_settings(argv)


def test_parse_settings_rejects_insecure_verify_with_ca_file():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--shared-secret",
        "secret-1",
        "--tls-insecure-skip-verify",
        "--tls-ca-file",
        "ca.pem",
    ]
    with pytest.raises(SystemExit, match="--tls-insecure-skip-verify cannot be used together with --tls-ca-file"):
        parse_settings(argv)


def test_parse_settings_accepts_mtls_client_pair():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--shared-secret",
        "secret-1",
        "--tls-client-cert-file",
        "client.crt",
        "--tls-client-key-file",
        "client.key",
        "--tls-ca-file",
        "ca.pem",
    ]
    settings = parse_settings(argv)
    assert settings.tls_client_cert_file == "client.crt"
    assert settings.tls_client_key_file == "client.key"
    assert settings.tls_ca_file == "ca.pem"
    assert settings.tls_insecure_skip_verify is False


def test_parse_settings_accepts_optional_device_id():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--device-id",
        "JETSON-001",
        "--shared-secret",
        "secret-1",
    ]
    settings = parse_settings(argv)
    assert settings.device_id == "JETSON-001"


def test_parse_settings_rejects_too_long_device_id():
    argv = [
        "--target",
        "api",
        "--ingest-url",
        "http://localhost:8000/v1/telemetry/ingest",
        "--drone-uid",
        "DRN-001",
        "--device-id",
        ("x" * 121),
        "--shared-secret",
        "secret-1",
    ]
    with pytest.raises(SystemExit, match="--device-id length must be <= 120"):
        parse_settings(argv)

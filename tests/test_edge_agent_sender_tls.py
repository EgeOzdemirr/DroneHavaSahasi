from unittest.mock import patch

from edge_agent.sender import TelemetrySender


def test_sender_uses_default_tls_verification():
    with patch("edge_agent.sender.httpx.Client") as client_cls:
        TelemetrySender(timeout_seconds=3.0)
        _, kwargs = client_cls.call_args
        assert kwargs["verify"] is True
        assert kwargs["cert"] is None


def test_sender_uses_custom_ca_file():
    with patch("edge_agent.sender.httpx.Client") as client_cls:
        TelemetrySender(timeout_seconds=3.0, tls_ca_file="/tmp/ca.pem")
        _, kwargs = client_cls.call_args
        assert kwargs["verify"] == "/tmp/ca.pem"
        assert kwargs["cert"] is None


def test_sender_uses_mtls_client_pair():
    with patch("edge_agent.sender.httpx.Client") as client_cls:
        TelemetrySender(
            timeout_seconds=3.0,
            tls_client_cert_file="/tmp/client.crt",
            tls_client_key_file="/tmp/client.key",
        )
        _, kwargs = client_cls.call_args
        assert kwargs["verify"] is True
        assert kwargs["cert"] == ("/tmp/client.crt", "/tmp/client.key")


def test_sender_allows_insecure_skip_verify():
    with patch("edge_agent.sender.httpx.Client") as client_cls:
        TelemetrySender(timeout_seconds=3.0, tls_insecure_skip_verify=True)
        _, kwargs = client_cls.call_args
        assert kwargs["verify"] is False


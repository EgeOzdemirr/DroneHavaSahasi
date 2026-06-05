from edge_agent.signer import build_signed_headers, canonical_signing_input, hmac_hex


def test_canonical_signing_input_shape():
    canonical = canonical_signing_input("DRN-001", "1710000000000", "nonce-abc", "hash-xyz")
    assert canonical == "DRN-001\n1710000000000\nnonce-abc\nhash-xyz"


def test_hmac_hex_is_deterministic():
    secret = "test-secret"
    canonical = "A\nB\nC\nD"
    assert hmac_hex(secret, canonical) == hmac_hex(secret, canonical)


def test_build_signed_headers_bridge_includes_bridge_token():
    raw_body = b'{"lat":41.0,"lon":29.0,"alt_m":100}'
    headers = build_signed_headers(
        drone_uid="DRN-001",
        device_id="JETSON-001",
        shared_secret="secret-1",
        raw_body=raw_body,
        target="bridge",
        bridge_token="bridge-token-1",
    )
    assert headers["X-Drone-Uid"] == "DRN-001"
    assert headers["X-Device-Id"] == "JETSON-001"
    assert headers["X-Sig-Version"] == "hmac-sha256-v1"
    assert "X-Signature" in headers
    assert headers["X-Bridge-Token"] == "bridge-token-1"


def test_build_signed_headers_api_excludes_bridge_token():
    raw_body = b'{"lat":41.0,"lon":29.0,"alt_m":100}'
    headers = build_signed_headers(
        drone_uid="DRN-001",
        device_id=None,
        shared_secret="secret-1",
        raw_body=raw_body,
        target="api",
        bridge_token="bridge-token-1",
    )
    assert "X-Device-Id" not in headers
    assert "X-Bridge-Token" not in headers


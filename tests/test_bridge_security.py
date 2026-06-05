from bridge.security import extract_forward_headers, token_valid


def test_token_valid() -> None:
    assert token_valid("abc", "abc")
    assert not token_valid("abc", "def")
    assert not token_valid(None, "abc")


def test_extract_forward_headers() -> None:
    headers = {
        "x-drone-uid": "DRN-001",
        "x-device-id": "JETSON-001",
        "x-ts": "123",
        "x-nonce": "n-1",
        "x-signature": "deadbeef",
        "x-sig-version": "hmac-sha256-v1",
        "x-extra": "ignore",
    }
    extracted, missing = extract_forward_headers(headers)
    assert missing == []
    assert extracted == {
        "X-Drone-Uid": "DRN-001",
        "X-Device-Id": "JETSON-001",
        "X-Ts": "123",
        "X-Nonce": "n-1",
        "X-Signature": "deadbeef",
        "X-Sig-Version": "hmac-sha256-v1",
    }


def test_extract_forward_headers_missing() -> None:
    extracted, missing = extract_forward_headers({"x-drone-uid": "DRN-001"})
    assert extracted == {"X-Drone-Uid": "DRN-001"}
    assert "X-Ts" in missing
    assert "X-Nonce" in missing
    assert "X-Signature" in missing
    assert "X-Sig-Version" in missing


def test_extract_forward_headers_optional_device_id_not_required() -> None:
    extracted, missing = extract_forward_headers(
        {
            "x-drone-uid": "DRN-001",
            "x-ts": "123",
            "x-nonce": "n-1",
            "x-signature": "deadbeef",
            "x-sig-version": "hmac-sha256-v1",
        }
    )
    assert missing == []
    assert "X-Device-Id" not in extracted

from app.security.csrf import csrf_matches
from app.security.hmac_signatures import body_sha256_hex, canonical_signing_input, sign_hmac_hex, verify_hmac_hex


def test_hmac_roundtrip() -> None:
    body = b'{"lat":41.0,"lon":29.0}'
    body_hash = body_sha256_hex(body)
    signing_input = canonical_signing_input("DRN-001", "1710000000000", "nonce-123", body_hash)
    signature = sign_hmac_hex("shared-secret", signing_input)
    assert verify_hmac_hex("shared-secret", signing_input, signature)


def test_csrf_match() -> None:
    token = "token-value"
    assert csrf_matches(token, token)
    assert not csrf_matches(token, "other")
    assert not csrf_matches(token, None)


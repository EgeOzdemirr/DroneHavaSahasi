import hashlib
import hmac


def body_sha256_hex(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def canonical_signing_input(drone_uid: str, ts_ms: str, nonce: str, body_hash_hex: str) -> str:
    return f"{drone_uid}\n{ts_ms}\n{nonce}\n{body_hash_hex}"


def sign_hmac_hex(secret: str, canonical_input: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_input.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac_hex(secret: str, canonical_input: str, provided_signature: str) -> bool:
    expected = sign_hmac_hex(secret, canonical_input)
    return hmac.compare_digest(expected, provided_signature.lower())


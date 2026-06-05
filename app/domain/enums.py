from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"


class DroneStatus(str, Enum):
    active = "active"
    inactive = "inactive"


class PlatformRole(str, Enum):
    recon = "recon"
    interceptor = "interceptor"


class KeyStatus(str, Enum):
    active = "active"
    inactive = "inactive"


class DeviceStatus(str, Enum):
    active = "active"
    revoked = "revoked"


class SignatureAlgorithm(str, Enum):
    hmac_sha256_v1 = "hmac-sha256-v1"


class FriendStatus(str, Enum):
    authorized = "AUTHORIZED"
    registered_not_authorized = "REGISTERED_NOT_AUTHORIZED"
    unknown = "UNKNOWN"
    suspicious = "SUSPICIOUS"


class TrackOrigin(str, Enum):
    cooperative = "cooperative"
    sensor_contact = "sensor_contact"


class ReasonCode(str, Enum):
    ok = "ok"
    not_in_registry = "not_in_registry"
    bad_signature = "bad_signature"
    replay_detected = "replay_detected"
    clock_skew = "clock_skew"
    no_active_mission = "no_active_mission"
    policy_violation = "policy_violation"
    link_lost = "link_lost"


class AlertStatus(str, Enum):
    open = "open"
    ack = "ack"
    resolved = "resolved"


class HostileDetectionStatus(str, Enum):
    open = "open"
    assigned = "assigned"
    resolved = "resolved"
    cancelled = "cancelled"


class InterceptTaskStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    completed = "completed"
    expired = "expired"


class FieldLayerType(str, Enum):
    base_perimeter = "base_perimeter"
    safe_corridor = "safe_corridor"
    patrol_area = "patrol_area"
    restricted_area = "restricted_area"
    custom = "custom"



from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db.models import Alert, TrackState
from app.domain.enums import AlertStatus, ReasonCode


def ensure_open_alert(
    db: Session,
    *,
    drone_uid: str,
    alert_type: str,
    message: str,
    reason_code: ReasonCode | None = None,
) -> Alert:
    stmt = select(Alert).where(
        and_(
            Alert.drone_uid == drone_uid,
            Alert.alert_type == alert_type,
            Alert.status == AlertStatus.open,
        )
    )
    current = db.execute(stmt).scalar_one_or_none()
    if current:
        return current

    alert = Alert(
        drone_uid=drone_uid,
        alert_type=alert_type,
        status=AlertStatus.open,
        message=message,
        reason_code=reason_code,
    )
    db.add(alert)
    db.flush()
    return alert


def resolve_open_alert(
    db: Session,
    *,
    drone_uid: str,
    alert_type: str,
) -> int:
    stmt = select(Alert).where(
        and_(
            Alert.drone_uid == drone_uid,
            Alert.alert_type == alert_type,
            Alert.status == AlertStatus.open,
        )
    )
    rows = db.execute(stmt).scalars().all()
    if not rows:
        return 0
    now = datetime.now(timezone.utc)
    for item in rows:
        item.status = AlertStatus.resolved
        item.acked_at = now
        item.acked_by = None
    return len(rows)


def maybe_raise_decision_alert(db: Session, drone_uid: str, reason_code: ReasonCode) -> None:
    if reason_code == ReasonCode.ok:
        return

    if reason_code in {ReasonCode.not_in_registry, ReasonCode.bad_signature, ReasonCode.replay_detected, ReasonCode.clock_skew}:
        alert_type = "unknown_or_spoof"
    elif reason_code == ReasonCode.no_active_mission:
        alert_type = "mission_mismatch"
    else:
        alert_type = "policy_or_system"
    message = f"{drone_uid}: {reason_code.value}"
    ensure_open_alert(db, drone_uid=drone_uid, alert_type=alert_type, message=message, reason_code=reason_code)


def raise_link_lost_alerts(db: Session, link_lost_seconds: int) -> int:
    now = datetime.now(timezone.utc)
    stmt = select(TrackState)
    tracks = db.execute(stmt).scalars().all()
    opened = 0
    for item in tracks:
        delta = now - item.last_seen_at
        if delta.total_seconds() <= link_lost_seconds:
            continue
        ensure_open_alert(
            db,
            drone_uid=item.drone_uid,
            alert_type="link_lost",
            message=f"{item.drone_uid}: no telemetry for {int(delta.total_seconds())} seconds",
            reason_code=ReasonCode.link_lost,
        )
        opened += 1
    return opened

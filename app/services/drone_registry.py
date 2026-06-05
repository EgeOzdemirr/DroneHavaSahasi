from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device, Drone, DroneKey, OperatorStation
from app.services.audit import write_audit_log


@dataclass
class DroneDeleteResult:
    ok: bool
    reason: str
    drone_uid: str | None = None


def delete_drone_from_registry(
    db: Session,
    *,
    drone_id: str,
    actor_username: str,
    via: str,
) -> DroneDeleteResult:
    drone = db.execute(select(Drone).where(Drone.id == drone_id)).scalar_one_or_none()
    if not drone:
        return DroneDeleteResult(ok=False, reason="not_found")

    linked_station = (
        db.execute(
            select(OperatorStation.id).where(OperatorStation.assigned_interceptor_drone_id == drone.id).limit(1)
        ).scalar_one_or_none()
        is not None
    )
    if linked_station:
        return DroneDeleteResult(ok=False, reason="linked_operator_station", drone_uid=drone.drone_uid)

    has_device = db.execute(select(Device.id).where(Device.drone_id == drone.id).limit(1)).scalar_one_or_none() is not None
    if has_device:
        return DroneDeleteResult(ok=False, reason="has_devices", drone_uid=drone.drone_uid)

    drone_uid = drone.drone_uid
    key_id = drone.key_id
    db.delete(drone)
    db.flush()

    key_ref_exists = db.execute(select(Drone.id).where(Drone.key_id == key_id).limit(1)).scalar_one_or_none() is not None
    if not key_ref_exists:
        key = db.execute(select(DroneKey).where(DroneKey.id == key_id)).scalar_one_or_none()
        if key:
            db.delete(key)

    db.commit()

    write_audit_log(
        db,
        actor_username=actor_username,
        action="drone_delete",
        entity_type="drone",
        entity_id=drone_id,
        details={"drone_uid": drone_uid, "via": via},
        success=True,
    )
    return DroneDeleteResult(ok=True, reason="deleted", drone_uid=drone_uid)

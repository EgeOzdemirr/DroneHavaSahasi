from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import TelemetryEvent


def purge_old_telemetry(db: Session, retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    stmt = delete(TelemetryEvent).where(TelemetryEvent.timestamp < cutoff)
    result = db.execute(stmt)
    return int(result.rowcount or 0)


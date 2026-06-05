from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.models import TelemetryIngestResponse, TelemetryPayload
from app.services.telemetry import TelemetryValidationError, process_telemetry

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])


@router.post("/ingest", response_model=TelemetryIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_telemetry(
    request: Request,
    payload: TelemetryPayload,
    db: Session = Depends(get_db),
) -> TelemetryIngestResponse:
    raw_body = await request.body()
    try:
        event = process_telemetry(
            db,
            headers={key.lower(): value for key, value in request.headers.items()},
            payload=payload,
            raw_body=raw_body,
        )
    except TelemetryValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return TelemetryIngestResponse(
        drone_uid=event.drone_uid,
        platform_role=event.platform_role,
        signature_valid=event.signature_valid,
        reason=event.reason_code,
        timestamp=event.timestamp,
    )

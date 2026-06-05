from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_roles
from app.config import get_settings
from app.db.models import User
from app.domain.enums import UserRole
from app.schemas.models import OpenSkyAircraftResponse
from app.services.opensky import OpenSkyConfigError, OpenSkyUnavailableError, fetch_opensky_aircraft

settings = get_settings()
router = APIRouter(prefix="/v1/air-traffic", tags=["air-traffic"])


@router.get("/opensky", response_model=list[OpenSkyAircraftResponse])
def list_opensky_aircraft(
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> list[OpenSkyAircraftResponse]:
    if not settings.opensky_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sivil hava trafiği katmanı kapalı.")

    try:
        return fetch_opensky_aircraft(settings)
    except OpenSkyConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except OpenSkyUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

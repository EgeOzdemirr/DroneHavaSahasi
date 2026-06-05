from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.models import User
from app.db.session import get_db
from app.domain.enums import PlatformRole, UserRole
from app.schemas.models import (
    PlaybackResponse,
    TrackStateResponse,
    TrackSummaryResponse,
)
from app.services.intercept_simulation import build_playback_response, build_track_list_response

router = APIRouter(prefix="/v1/tracks", tags=["tracks"])


@router.get("", response_model=list[TrackStateResponse])
def list_tracks(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> list[TrackStateResponse]:
    return build_track_list_response(db)


@router.get("/summary", response_model=TrackSummaryResponse)
def track_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> TrackSummaryResponse:
    rows = build_track_list_response(db)
    recon = 0
    interceptor = 0
    last_update: datetime | None = None
    for row in rows:
        if row.platform_role == PlatformRole.recon:
            recon += 1
        elif row.platform_role == PlatformRole.interceptor:
            interceptor += 1
        if last_update is None or row.updated_at > last_update:
            last_update = row.updated_at
    return TrackSummaryResponse(
        total=len(rows),
        recon=recon,
        interceptor=interceptor,
        last_update=last_update,
    )


@router.get("/{drone_uid}/playback", response_model=PlaybackResponse)
def playback(
    drone_uid: str,
    minutes: int = 60,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.admin, UserRole.operator, UserRole.viewer)),
) -> PlaybackResponse:
    if minutes < 1:
        minutes = 1
    if minutes > 360:
        minutes = 360
    return build_playback_response(db, drone_uid=drone_uid, minutes=minutes)

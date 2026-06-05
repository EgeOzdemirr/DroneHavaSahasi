from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import (
    air_traffic,
    alerts,
    audit,
    auth,
    demo,
    devices,
    drones,
    field_layers,
    hostile_detections,
    intercept_tasks,
    operator_stations,
    recon,
    telemetry,
    tracks,
    ui,
)
from app.config import get_settings
from app.db.session import SessionLocal
from app.services.background import background_maintenance
from app.services.bootstrap import ensure_bootstrap_admin

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        ensure_bootstrap_admin(db)

    stop_event = asyncio.Event()
    task = asyncio.create_task(background_maintenance(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await task


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/docs") or request.url.path.startswith("/redoc"):
        # FastAPI docs load Swagger/ReDoc assets from CDN and use inline bootstrap script.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' https://cdn.jsdelivr.net https://fastapi.tiangolo.com; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self';"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://unpkg.com; "
            "img-src 'self' data: blob: https://tiles.openfreemap.org; "
            "connect-src 'self' https://tiles.openfreemap.org https://fonts.openmaptiles.org https://unpkg.com; "
            "worker-src 'self' blob:; "
            "child-src blob:; "
            "frame-ancestors 'none'; "
            "form-action 'self';"
        )
    return response


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/login")

app.mount("/ui/static", StaticFiles(directory="app/ui/static"), name="ui-static")

app.include_router(auth.router)
app.include_router(drones.router)
app.include_router(devices.router)
app.include_router(field_layers.router)
app.include_router(demo.router)
app.include_router(telemetry.router)
app.include_router(tracks.router)
app.include_router(recon.router)
app.include_router(hostile_detections.router)
app.include_router(intercept_tasks.router)
app.include_router(operator_stations.router)
app.include_router(air_traffic.router)
app.include_router(alerts.router)
app.include_router(audit.router)
app.include_router(ui.router)

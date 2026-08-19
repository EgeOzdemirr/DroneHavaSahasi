# Friend Drone MVP

Security-first airspace control center MVP for a single base network. The current workflow is centered on signed drone telemetry, recon contact reporting, hostile detection tracking, operator stations, and human-approved intercept tasks.

## Components

- `api`: FastAPI monolith (`/v1/*`, `/v2/*`, `/ui/*`)
- `bridge`: HTTP telemetry bridge (`/bridge/v1/*`) with token gate and Redis retry queue
- `postgres`: PostgreSQL + PostGIS
- `redis`: nonce replay protection cache and bridge retry/DLQ backend
- `edge_agent`: Jetson-friendly telemetry forwarder with local SQLite spool

## Live Demo

- **<https://hava-sahasi-demo.onrender.com/ui/login>**

The demo is publicly reachable but not publicly usable: every `/ui/*`, `/v1/*` and
`/v2/*` endpoint requires authentication, so visitors see only the login screen unless
they were given credentials.

Visitors sign in with a read-only `viewer` account provisioned from
`BOOTSTRAP_VIEWER_USERNAME` / `BOOTSTRAP_VIEWER_PASSWORD`. That role opens the control
center in read-only mode: the map, tracks, hostile detections, intercept tasks, alerts
and audit trail are all visible, but every write endpoint rejects the role, so a visitor
cannot delete a drone, reset the demo, edit field layers or take over the account. The
account is re-synced from the environment on every startup, so it cannot be locked out.
Admin credentials are for the operator of the deployment only.

Free-tier note: the instance sleeps after 15 minutes of inactivity, so the first
request can take up to ~50 seconds.

Deploy your own instance from `render.yaml`: see `docs/PUBLIC_DEMO_DEPLOY.md`.

## Quick Start

### Windows quick launcher

For a double-click startup flow, use `start-hava-sahasi.cmd` from the repository root.
It starts Docker Desktop if needed, runs `docker compose up -d --build`, waits for
the API, and opens `http://localhost:8000/ui/login` in your default browser.
If Google Chrome is installed it is used first; otherwise the system default browser is used.

Prerequisites:

- Docker Desktop is installed.
- `.env` exists in the repository root. If needed, create it with `Copy-Item .env.example .env`.

1. Create local env file:
   - Windows PowerShell: `Copy-Item .env.example .env`
   - Linux/macOS: `cp .env.example .env`
2. Start stack:
   - `docker compose up --build`  1"  1
3. API/UI:
   - API docs: `http://localhost:8000/docs`
   - UI login: `http://localhost:8000/ui/login`
   - Control center: `http://localhost:8000/ui/control-center`

   
   - Operator panel: `http://localhost:8000/ui/operator`
   - Drone registry: `http://localhost:8000/ui/drones`
   - Bridge docs: `http://localhost:8 q2 mkö00/docs`
4. Bootstrap admin from `.env`:
   - username: `BOOTSTRAP_ADMIN_USERNAME`
   - password: `BOOTSTRAP_ADMIN_PASSWORD`

Previous tactical and mission UI paths are compatibility redirects to the current control-center workflow; do not treat them as active screens.

## Current Operational Flow

1. Register recon and interceptor drones.
2. Provision edge devices when device health tracking is needed.
3. Create operator stations and assign active interceptor drones.
4. Send signed telemetry from recon/interceptor drones.
5. Report a recon contact with bearing/range/elevation.
6. The system creates or updates a hostile detection and assigns an intercept task to the nearest eligible operator station.
7. The operator accepts, rejects, or completes the task from the operator panel.

The system is decision support only. It does not autonomously command a physical drone.

## Public API Surface

- `POST /v1/telemetry/ingest`
- `GET /v1/tracks`
- `GET /v1/tracks/summary`
- `GET /v1/tracks/{drone_uid}/playback`
- `POST /v1/recon/contacts`
- `GET /v1/hostile-detections`
- `DELETE /v1/hostile-detections/{id}`
- `GET /v1/intercept-tasks`
- `GET /v1/intercept-tasks/me`
- `POST /v1/intercept-tasks/{id}/accept`
- `POST /v1/intercept-tasks/{id}/reject`
- `POST /v1/intercept-tasks/{id}/complete`
- `GET /v1/operator-stations`
- `POST /v1/operator-stations`
- `PATCH /v1/operator-stations/{station_id}`
- `POST /v1/drones`
- `GET /v1/drones`
- `PATCH /v1/drones/{drone_id}`
- `DELETE /v1/drones/{drone_id}`
- `POST /v2/devices/provision`
- `POST /v2/devices/{device_id}/rotate-cert`
- `GET /v2/devices/{device_id}/health`
- `GET/POST /ui/drones`
- `GET /ui/control-center`
- `GET /ui/operator`

## Decision-Maker Demo

The demo does not require a real drone. With `DEMO_MODE_ENABLED=true`, the control center can seed a scripted scenario, create demo operators, create a hostile target, assign a task, and simulate interceptor movement after operator acceptance.

1. Start stack:

```powershell
docker compose up -d --build
```

2. Log in as admin:
   - URL: `http://localhost:8000/ui/login`
   - Username: `BOOTSTRAP_ADMIN_USERNAME`
   - Password: `BOOTSTRAP_ADMIN_PASSWORD`

3. Use the `Sunum Akisi` panel in the control center:
   - Reset demo
   - Seed scenario
   - Create target detection
   - Open operator panel
   - Accept the task
   - Watch simulated interceptor movement

Demo operator credentials:

- `demo_operator_1 / ***REMOVED***`
- `demo_operator_2 / ***REMOVED***`
- `demo_operator_3 / ***REMOVED***`

Demo mode settings:

- `DEMO_MODE_ENABLED=true`: demo panel and `/v1/demo/*` endpoints are enabled.
- `DEMO_MODE_ENABLED=false`: demo panel is hidden and demo endpoints return not found.
- `DEMO_INTERCEPTOR_SPEED_MPS=95`: simulated interceptor speed.
- `DEMO_INTERCEPTOR_MIN_DURATION_SECONDS=25`: minimum visible movement duration.

For field/prod rehearsal, set `DEMO_MODE_ENABLED=false`.

## Field Pilot Quick Path

1. Preflight:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\preflight_check.ps1 -EnvPath .env
```

2. Stack:

```powershell
docker compose up -d --build
```

3. E2E smoke (bridge + signature + replay + optional device health):

```powershell
python .\scripts\vpn_mtls_e2e_smoke.py --api-base-url http://localhost:8000 --bridge-url http://localhost:8100 --bridge-token <bridge_token> --device-id JETSON-PILOT-001 --allow-bootstrap-password-change
```

4. Control center:

```text
http://localhost:8000/ui/control-center
```

5. Operator panel:

```text
http://localhost:8000/ui/operator
```

See `docs/FIELD_PILOT_RUNBOOK.md` for the full control-center field flow.

## Project Tracking Docs

- `docs/PLAN.md`: Current purpose, architecture, roadmap, scope boundaries, and near-term priorities.
- `docs/STATUS.md`: Current status table (`Yapildi / Yapiliyor / Bekliyor / Riskler / Sonraki 3 Adim`).
- `docs/HANDOFF_LOG.md`: Append-only session handoff log.
- `docs/FIELD_PILOT_RUNBOOK.md`: Field pilot procedure.

New session checklist:

1. Read `docs/PLAN.md`.
2. Read `docs/STATUS.md`.
3. Check `git status --short`.

## Security Defaults

- Telemetry signing: `HMAC-SHA256` (`X-Sig-Version: hmac-sha256-v1`)
- Replay protection: `X-Nonce` + Redis TTL
- Auth: JWT bearer or HttpOnly cookie (`fd_access_token`)
- CSRF: double-submit token (`fd_csrf_token` + `X-CSRF-Token`)
- Security headers: CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`
- Prod hardening blocks weak defaults in `ENVIRONMENT=prod` for JWT secret, bridge token, Fernet master key, admin password, cookies, and CORS.

## Bootstrap Accounts

- Bootstrap admin and (optionally) a read-only viewer are provisioned at startup
  from environment variables and re-synced to those values on every boot, so a lost
  password is recovered by changing the env value and restarting — no lockout, no
  manual database edits (`app/services/bootstrap.py`).
- The password-change flow itself still exists for accounts created with
  `must_change_password=True`:
  - `POST /v1/auth/change-password` — body `{"current_password":"...","new_password":"..."}`
  - UI redirects to `/ui/change-password` when required.
  - Role-protected endpoints return `403 password_change_required` until changed.

## Telemetry Ingest Contract

- Endpoint: `POST /v1/telemetry/ingest`
- Headers:
  - `X-Drone-Uid`
  - `X-Device-Id` (optional, for v2 device health tracking)
  - `X-Ts` (Unix ms, UTC)
  - `X-Nonce`
  - `X-Signature`
  - `X-Sig-Version: hmac-sha256-v1`
- Body:
  - `lat`, `lon`, `alt_m`, `speed_mps`, `heading_deg`, `seq`, `source`

Canonical input:

```text
X-Drone-Uid + "\n" + X-Ts + "\n" + X-Nonce + "\n" + SHA256_HEX(raw_body_bytes)
```

Accepted telemetry writes `TelemetryEvent` and updates `TrackState` with the drone's `platform_role` (`recon` or `interceptor`).

## Recon Contact / Hostile Detection Contract

Recon contact reporting turns an observed bearing/range/elevation into a hostile target coordinate.

- Endpoint: `POST /v1/recon/contacts`
- Body:
  - `recon_drone_uid`
  - `contact_id`
  - `bearing_mil`
  - `range_m`
  - `elevation_mil`
  - `confidence`
  - `timestamp` (optional)

Behavior:

- The recon drone must have a recent track and `platform_role=recon`.
- The service computes target lat/lon/alt from the recon track and reported contact geometry.
- A `hostile_detections` row is created or updated for the `(recon_drone_uid, contact_id)` pair.
- If an eligible active operator station exists, the detection is assigned and an `intercept_tasks` row is opened.
- Operators can accept, reject, or complete assigned tasks.

Related endpoints:

- `GET /v1/hostile-detections`
- `DELETE /v1/hostile-detections/{id}`
- `GET /v1/intercept-tasks`
- `GET /v1/intercept-tasks/me`
- `POST /v1/intercept-tasks/{id}/accept`
- `POST /v1/intercept-tasks/{id}/reject`
- `POST /v1/intercept-tasks/{id}/complete`

## Operator Stations

Operator stations connect an operator user, a position, and an interceptor drone.

- `GET /v1/operator-stations`
- `POST /v1/operator-stations`
- `PATCH /v1/operator-stations/{station_id}`

Rules:

- Station user must have role `operator`.
- Assigned drone must have `platform_role=interceptor`.
- Only active stations with active interceptor drones are eligible for automatic task assignment.

## Bridge Contract

- Endpoint: `POST /bridge/v1/telemetry/ingest`
- Required extra header:
  - `X-Bridge-Token`
- Telemetry headers and body are the same as API ingest.
- Behavior:
  - upstream `2xx/4xx`: response passes through
  - upstream `5xx/timeout`: event queued in Redis, response `202 {"queued": true, ...}`

## Device V2 API

Management endpoints for edge device lifecycle:

- `POST /v2/devices/provision`
  - body: `{"device_id":"JETSON-001","drone_uid":"DRN-001","cert_fingerprint":"sha256:..."}`
- `POST /v2/devices/{device_id}/rotate-cert`
  - body: `{"cert_fingerprint":"sha256:..."}`
- `GET /v2/devices/{device_id}/health`
  - returns `online`, `stale`, `never_seen`, or `revoked` health state plus last seen/error fields

`X-Device-Id` is optional for telemetry ingest. If present and matched to a provisioned device, the API updates `last_seen_at` or `last_error_reason`.

## Ops Notes

- Link-lost monitor runs every 5 seconds (`LINK_LOST_SECONDS` threshold).
- Telemetry retention purge runs hourly (`RETENTION_DAYS` cutoff).
- Critical admin and task actions are recorded in `audit_log`.
- Playback is available through `GET /v1/tracks/{drone_uid}/playback?minutes=60`.
- OpenSky overlay is controlled with `OPENSKY_ENABLED` and related `OPENSKY_*` settings.

## Edge Agent MVP (Jetson)

Use the `edge_agent` package for production-like telemetry forwarding with local SQLite spool and retry.

MAVLink UART mode:

```powershell
python -m edge_agent `
  --input-mode mavlink-uart `
  --mavlink-device /dev/ttyTHS1 `
  --mavlink-baud 57600 `
  --target bridge `
  --ingest-url http://localhost:8100/bridge/v1/telemetry/ingest `
  --bridge-token change-me-bridge-token `
  --drone-uid DRN-REAL-001 `
  --device-id JETSON-REAL-001 `
  --shared-secret "<shared_secret>" `
  --spool-db-path ./edge_agent_spool.db `
  --rate-hz 1.0
```

UDP fallback mode:

```powershell
python -m edge_agent `
  --input-mode udp-json `
  --udp-host 0.0.0.0 `
  --udp-port 15000 `
  --target bridge `
  --ingest-url http://localhost:8100/bridge/v1/telemetry/ingest `
  --bridge-token change-me-bridge-token `
  --drone-uid DRN-LAB-001 `
  --device-id JETSON-LAB-001 `
  --shared-secret "<shared_secret>"
```

Behavior:

- Every outgoing packet is signed with `hmac-sha256-v1`.
- Packets are first written to local SQLite spool.
- `2xx`: delete from outbox.
- `4xx`: drop into dead-letter without retry.
- `5xx`/network error: retry with backoff; max attempts go to dead-letter.

TLS/mTLS options:

- `--tls-ca-file <path>`: custom CA bundle for server verification.
- `--tls-client-cert-file <path>` + `--tls-client-key-file <path>`: client cert/key pair for mTLS.
- `--tls-insecure-skip-verify`: disable TLS verification for dev only.

## Jetson Deployment (systemd + watchdog)

Production-like deployment templates:

- `deploy/systemd/edge-agent.service`
- `deploy/systemd/edge-agent.env.example`

Recommended install flow on Jetson:

```bash
sudo mkdir -p /opt/friend_drone /etc/friend-drone /var/lib/friend-drone
sudo cp -r ./ /opt/friend_drone
sudo cp deploy/systemd/edge-agent.service /etc/systemd/system/edge-agent.service
sudo cp deploy/systemd/edge-agent.env.example /etc/friend-drone/edge-agent.env
sudo chmod 600 /etc/friend-drone/edge-agent.env
sudo systemctl daemon-reload
sudo systemctl enable edge-agent
sudo systemctl restart edge-agent
sudo systemctl status edge-agent --no-pager
```

Watchdog/health commands:

```bash
sudo journalctl -u edge-agent -f
sudo systemctl restart edge-agent
sudo systemctl is-enabled edge-agent
```

## VPN + mTLS Runbook

For secure field deployment:

- `docs/VPN_MTLS_RUNBOOK.md`
- `docs/VPN_MTLS_E2E_CHECKLIST.md`
- `deploy/security/bridge-nginx-mtls.conf.example`
- `deploy/security/wireguard/server-wg0.conf.example`
- `deploy/security/wireguard/jetson-wg0.conf.example`

E2E smoke:

```powershell
python .\scripts\vpn_mtls_e2e_smoke.py --api-base-url http://localhost:8000 --bridge-url http://localhost:8100 --bridge-token <bridge_token> --device-id JETSON-PILOT-001 --allow-bootstrap-password-change
```

## Secret Rotation

Runbook:

- `docs/SECRET_ROTATION_RUNBOOK.md`

Scripts:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\generate_secrets.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\validate_env_secrets.ps1 -EnvPath .env
powershell -ExecutionPolicy Bypass -File .\scripts\ci_secret_rotation_check.ps1
```

GitHub Actions workflow:

- `.github/workflows/quality-gates.yml`

## Real-World Relay (Field-First)

For actual flight operations, use `scripts/field_relay.py` to forward real telemetry to bridge/API.

1. Provision drone and keep returned `drone_uid` + `shared_secret`.
2. Start relay on telemetry source host:

```powershell
python .\scripts\field_relay.py `
  --target bridge `
  --ingest-url http://localhost:8100/bridge/v1/telemetry/ingest `
  --bridge-token change-me-bridge-token `
  --drone-uid DRN-REAL-001 `
  --shared-secret "<shared_secret>" `
  --input-mode udp-json `
  --udp-host 0.0.0.0 `
  --udp-port 15000
```

3. Feed relay with JSON packets (UDP or stdin):

```json
{"lat":41.015,"lon":28.979,"alt_m":120.0,"speed_mps":14.2,"heading_deg":95.0,"seq":10,"source":"gcs"}
```

4. Verify:
   - `GET /v1/tracks` shows live tracks.
   - `GET /v1/tracks/summary` updates.
   - Control center map reflects recon/interceptor movement.

## Tests

Run the current test suite:

```powershell
python -m pytest -q
```

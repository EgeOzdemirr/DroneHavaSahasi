# FIELD PILOT RUNBOOK (Boluk Seviyesi)

Bu runbook, tek us/tek ag senaryosunda control center + operator paneli akisini sahada tekrar edilebilir sekilde calistirmak icin kullanilir.

## 1) Gun Basi Acilis

1. `.env` degerlerini guncelle ve secret kontrolu kos:
   - `powershell -ExecutionPolicy Bypass -File .\scripts\validate_env_secrets.ps1 -EnvPath .env`
2. Stack'i baslat:
   - `docker compose up -d --build`
3. Preflight kos:
   - `powershell -ExecutionPolicy Bypass -File .\scripts\preflight_check.ps1 -EnvPath .env`
4. UI ve API erisimi dogrula:
   - `http://localhost:8000/ui/login`
   - `http://localhost:8000/ui/control-center`
   - `http://localhost:8000/ui/operator`
   - `http://localhost:8000/docs`
5. Zorunlu parola degisimi varsa once tamamla:
   - `http://localhost:8000/ui/change-password`

## 2) Demo ve Saha Profili Ayrimi

- Demo/sunum icin `DEMO_MODE_ENABLED=true` kullanilabilir.
- Saha/prod provasi icin `DEMO_MODE_ENABLED=false` kullanilmalidir.
- Demo modunda gercek drone komutu gonderilmez; hedef, operator gorevi ve onleyici hareketi simule edilir.
- Gercek saha akisi icin kesif drone telemetrisi, contact kaynagi, VPN/mTLS ve operator prosedurleri ayri ayri dogrulanmalidir.

## 3) Drone ve Cihaz Hazirligi

1. Admin/operator olarak login ol.
2. UI uzerinden drone kaydi olustur:
   - `GET/POST /ui/drones`
3. API ile drone kaydi gerekiyorsa:
   - `POST /v1/drones`
4. Edge cihaz takip edilecekse:
   - `POST /v2/devices/provision`
5. Edge agent veya field relay icin `drone_uid`, `shared_secret`, opsiyonel `device_id` degerlerini kaydet.

## 4) Operator Station Hazirligi

1. Operator kullanicilarini ve onleyici drone kayitlarini hazirla.
2. Her operator icin istasyon kaydi olustur veya guncelle:
   - `GET /v1/operator-stations`
   - `POST /v1/operator-stations`
   - `PATCH /v1/operator-stations/{station_id}`
3. Her aktif istasyonda:
   - Kullanici rolu `operator` olmali.
   - Bagli drone `interceptor` rolunde ve aktif olmali.
   - Istasyon lat/lon saha gercegine uygun olmali.

## 5) Canli Telemetri Dogrulama

1. Edge agent veya smoke script ile imzali telemetri gonder:
   - `python .\scripts\vpn_mtls_e2e_smoke.py --api-base-url http://localhost:8000 --bridge-url http://localhost:8100 --bridge-token <bridge_token> --device-id <device_id> --allow-bootstrap-password-change`
2. Beklenenler:
   - Gecerli paket `reason=ok` ile kabul edilir.
   - Replay denemesi `replay_detected` ile reddedilir.
   - Gecersiz bridge token `401` doner.
3. Control center uzerinden izleri dogrula:
   - `GET /v1/tracks`
   - `GET /v1/tracks/summary`
   - `http://localhost:8000/ui/control-center`

## 6) Recon Contact ve Onleme Gorevi

1. Kesif drone izinin guncel oldugunu kontrol et:
   - `GET /v1/tracks`
2. Kesif drone rolunun `recon` oldugunu dogrula.
3. Hedef temasi gir:
   - `POST /v1/recon/contacts`
   - Zorunlu alanlar: `recon_drone_uid`, `contact_id`, `bearing_mil`, `range_m`, `elevation_mil`, `confidence`
4. Sistem beklenen sekilde:
   - Hedef koordinatini hesaplar.
   - `hostile_detections` kaydi olusturur veya gunceller.
   - En uygun aktif operator station secilirse `intercept_tasks` kaydi acar.
5. Control center kontrolu:
   - `GET /v1/hostile-detections`
   - `GET /v1/intercept-tasks`
   - `http://localhost:8000/ui/control-center`
6. Operator kontrolu:
   - `GET /v1/intercept-tasks/me`
   - `POST /v1/intercept-tasks/{task_id}/accept`
   - `POST /v1/intercept-tasks/{task_id}/reject`
   - `POST /v1/intercept-tasks/{task_id}/complete`
   - `http://localhost:8000/ui/operator`

## 7) Alarm, Audit ve Gun Sonu Kontrol

1. Acik alarmlari kontrol et:
   - `GET /v1/alerts`
2. Operasyonel teyit sonrasi gerekiyorsa ACK et:
   - `POST /v1/alerts/{id}/ack`
3. Kritik UID'ler icin playback al:
   - `GET /v1/tracks/{drone_uid}/playback?minutes=60`
4. Audit kayitlarini kontrol et:
   - `GET /v1/audit-logs`
5. Saha sonucunu `docs/HANDOFF_LOG.md` dosyasina append-only kaydet.

## 8) Ariza Durumunda Hizli Triage

1. Bridge/API erisim sorunu:
   - `docker compose ps`
   - `docker compose logs api bridge --tail=100`
2. Migration drift:
   - `docker compose exec -T api alembic current`
   - `docker compose exec -T api alembic heads`
3. Secret kaynakli baslatma hatasi:
   - `powershell -ExecutionPolicy Bypass -File .\scripts\validate_env_secrets.ps1 -EnvPath .env`
4. VPN/mTLS sorunu:
   - WireGuard peer/route durumunu kontrol et.
   - mTLS CA/server/client cert zincirini kontrol et.
5. Edge veri kesintisi:
   - Edge spool outbox/DLQ durumunu kontrol et.
   - Saat senkronunu (NTP/GNSS) kontrol et.

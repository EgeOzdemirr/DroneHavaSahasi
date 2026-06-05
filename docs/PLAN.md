# Proje Plani (Kalici Takip)

Son guncelleme: 2026-05-05 (UTC+3)

## 1) Amac ve Mevcut Durum

Bu proje tek us/tek ag senaryosunda hava sahasi farkindaligi, dost drone takibi ve insan-onayli onleme gorev destegi icin guvenlik temelli bir kontrol merkezi platformudur.

Mevcut cekirdek yetenekler:

- Imzali telemetri dogrulama: HMAC, replay korumasi, clock skew kontrolu.
- Drone registry ve device lifecycle: drone kaydi, anahtar uretimi/rotasyonu, cihaz provision/health akisi.
- Control center UI: kesif ve onleyici drone izleri, dusman hedef tespitleri, gorev durumu ve demo/saha panelleri.
- Operator UI: operatore atanmis onleme gorevlerini kabul, reddetme ve tamamlama akisi.
- Recon contact ingest: kesif drone izinden bearing/range/elevation ile dusman hedef koordinati uretimi.
- Hostile detection ve intercept task akisi: hedef tespiti, en uygun operator istasyonuna atama, gorev lifecycle takibi.
- Alert, audit, RBAC, CSRF, bridge retry/DLQ, edge agent, VPN/mTLS operasyon paketi.

Mevcut kritik sinirlar:

- Sistem halen karar destek rolundedir; otonom angajman veya gercek drone komutu gonderimi yoktur.
- Dusman hedef tespiti dogrudan sensor fusion degil; mevcut akista kesif drone veya demo girdisiyle hedef temasi sisteme girilir.
- Prod saha kullanimi icin gercek sensor/AI tespit kaynagi, autopilot komut adaptoru, VPN/mTLS ve saha emniyet prosedurleri tamamlanmalidir.

## 2) Guncel Mimari Durum

- API: FastAPI moduler monolith (`/v1/*`, `/v2/*`, `/ui/*`).
- Bridge: ayrik servis (`/bridge/v1/*`), token gate ve pass-through signed telemetry.
- DB: PostgreSQL + PostGIS tabanli runtime veri modeli.
- Queue/cache: Redis (nonce, bridge retry, DLQ).
- Auth: local JWT + RBAC + HttpOnly UI cookie + CSRF.
- UI: `/ui/control-center`, `/ui/operator`, `/ui/drones`.
- Saha rolu: insan-onayli karar destek ve takip; otomatik/kinetik angajman kapsam disi.

Gecerli ana API/UI yuzeyi:

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
- `GET/POST/PATCH /v1/operator-stations`
- `GET/POST /ui/drones`
- `GET /ui/control-center`
- `GET /ui/operator`

## 3) Tamamlanan Fazlar

- Sprint 1: Registry, signed telemetry ingest, track state ve temel UI akisi.
- Sprint 2: HMAC, replay, JWT/RBAC, CSRF, audit ve alert altyapisi.
- Sprint 3: Offline/online harita altyapisi, playback ve demo veri akislari.
- Sprint 4: Bridge servisi, token gate, retry queue ve DLQ.
- Sprint 5A: Bootstrap password enforcement ve secret rotation paketi.
- Sprint 5B: Field pilot runbook, preflight, edge `device-id`, VPN/mTLS smoke paketi.
- Control-center refactor: recon/hostile detection/intercept task/operator station modeli ve UI akisi.

## 4) Yakin Donem Oncelik

- P1: Gercek Jetson + VPN/mTLS saha pilotunu yeni control-center akisiyle tam gun kosmak ve raporlamak.
- P1: Gercek kesif drone telemetrisi ve sensor/AI contact kaynagini `POST /v1/recon/contacts` sozlesmesine baglamak.
- P1: Demo modu/prod modu ayrimini operasyonel olarak sertlestirmek (`DEMO_MODE_ENABLED=false`, prod secret/cookie/CORS profili).
- P1: Operator station lifecycle icin saha runbook'u ve admin ekran davranisini tamamlamak.
- P2: Ops gozlemlenebilirlik: API/bridge latency, queue depth, task SLA, alert SLA, audit export.
- P2: HA/failover PoC: API, Postgres, Redis ve bridge icin minimum dayanriklilik plani.
- P2: Branch protection ile quality gates'i zorunlu hale getirmek.

## 5) Evrim Plani (6-12-24 Ay)

### 6 Ay

- Jetson edge agent saha stabilizasyonu ve watchdog dogrulamasi.
- VPN + mTLS zorunlu operasyon profili.
- Gercek recon/contact entegrasyonu ve operator station saha pilotu.
- Demo akisi ile saha akisini dokuman ve config seviyesinde net ayirma.

### 12 Ay

- Coklu operator/fleet gorunumu.
- Gelismis gorev onceliklendirme ve hedef davranis skorlama.
- Ops gozlemlenebilirlik ve olay sonrasi raporlama.
- Device lifecycle olgunlastirma: provision, rotate, revoke, cert expiry takibi.

### 24 Ay

- Cok us/federasyon.
- SOC/SIEM entegrasyonu.
- Yuksek erisilebilirlik ve disaster drill.
- Kurumsal IdP/OIDC ve detayli denetim raporlari.

## 6) Kapsam Disi (Bu Fazda)

- Otonom veya kinetik angajman.
- Tam olcekli radar/RF/EO-IR sensor fusion urunlesmesi.
- Gercek autopilot komut adaptoru olmadan fiziksel onleme komutu.
- Kurumsal Kubernetes/HA production platformuna tam gecis.

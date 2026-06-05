# Proje Durum Takibi

Son guncelleme: 2026-05-05 00:00 (UTC+3)
Kaynak oturum notu: Dokumanlar mevcut control-center / operator / recon contact / intercept task refactor kod yuzeyine gore guncellendi.

## Yapildi

- [P1][owner: backend] Signed telemetry ingest aktif: HMAC, nonce replay korumasi, clock skew kontrolu ve `X-Device-Id` health update akisi calisiyor.
- [P1][owner: security] JWT/RBAC, UI cookie auth, CSRF, security headers ve bootstrap password enforcement devrede.
- [P1][owner: backend] Drone registry, key generation/rotation, drone patch/delete ve UI drone registry akislari mevcut.
- [P1][owner: backend] Device v2 endpointleri mevcut: `POST /v2/devices/provision`, `POST /v2/devices/{device_id}/rotate-cert`, `GET /v2/devices/{device_id}/health`.
- [P1][owner: backend] Track API mevcut: `GET /v1/tracks`, `GET /v1/tracks/summary`, `GET /v1/tracks/{drone_uid}/playback`.
- [P1][owner: backend] Recon contact ingest mevcut: `POST /v1/recon/contacts` kesif drone izinden hedef koordinati uretir.
- [P1][owner: backend] Hostile detection API mevcut: listeleme, detay ve admin delete akisi.
- [P1][owner: backend] Intercept task lifecycle mevcut: listeleme, operatore ozel listeleme, accept/reject/complete akislari.
- [P1][owner: backend] Operator station API mevcut: listeleme, olusturma ve guncelleme; istasyonlar onleyici drone ile baglanir.
- [P1][owner: ui] `/ui/control-center` ve `/ui/operator` ekranlari mevcut; `/ui/drones` uzerinden registry isleri yapilabiliyor.
- [P1][owner: demo] Karar verici demo akisi mevcut: senaryo kurma, hedef tespiti olusturma, operator atama ve onleyici hareket simulatesi.
- [P1][owner: platform] Bridge servisi token gate, signed pass-through, Redis retry queue ve DLQ ile devrede.
- [P1][owner: edge] Edge agent MVP mevcut: MAVLink UART, UDP fallback, SQLite spool, retry, TLS/mTLS flags, opsiyonel `--device-id`.
- [P1][owner: ops] Secret rotation, preflight, VPN/mTLS runbook ve E2E smoke script paketi mevcut.
- [P2][owner: platform] CI quality gates mevcut: pytest ve secret rotation script check workflow'u.
- [P2][owner: integrations] OpenSky sivil hava trafigi overlay endpointi ve servis testleri mevcut.

## Mevcut Mimari Notu

- Eski mission/assignment tabanli operasyon modeli bu refactor sonrasi aktif yuzey degildir.
- Eski sensor-contact/correlation modeli aktif yuzey degildir; mevcut detection akisi `POST /v1/recon/contacts` ve `hostile_detections` modeliyle temsil edilir.
- Eski ayrik tactical ekran aktif ana ekran degildir; ana UI yuzeyi control center ve operator panelidir.

## Yapiliyor

- [P1][owner: ops/security] Gercek Jetson uzerinde VPN + mTLS saha dogrulamasi ve runbook sonuc kaydi.
- [P1][owner: backend/integrations] Gercek kesif drone telemetrisi ve sensor/AI contact kaynaginin recon contact sozlesmesine baglanmasi.
- [P1][owner: ui/ops] Control center ve operator paneli icin saha kullanimi odakli kisa operator prosedurleri.
- [P2][owner: platform] Quality gates'in branch protection ile zorunlu hale getirilmesi.

## Bekliyor

- [P1][owner: ops] Demo modu kapali prod profilinin saha provasi.
- [P1][owner: backend] Operator station lifecycle icin daha net admin/ops kabul kriterleri.
- [P1][owner: integrations] Gercek sensor/AI contact adapter tasarimi.
- [P2][owner: platform] HA/operasyonel dayaniklilik: DB/Redis/API/bridge failover stratejisi.
- [P2][owner: observability] Latency, queue depth, task SLA, alert SLA ve audit export.

## Riskler / Blokerler

- [P1][owner: ops] Gercek saha testleri yapilmadan demo akisi operasyonel yeterlilik olarak kabul edilmemeli.
- [P1][owner: security] Prod ortamda secret rotation ve `DEMO_MODE_ENABLED=false` uygulanmazsa risk devam eder.
- [P2][owner: edge] PX4/ArduPilot telemetry mapping farklari gercek ucus kontrolcusu entegrasyonunu geciktirebilir.
- [P2][owner: ops] Zaman senkronizasyonu (NTP/GNSS drift) clock skew kaynakli false reject uretebilir.
- [P2][owner: integrations] OpenSky dis bagimliligi saha/offline kullanimda kontrollu degrade edilmeli.

## Sonraki 3 Adim

1. [P1][owner: ops/security] Gercek Jetson cihazinda VPN+mTLS smoke kos, control center uzerinden track/gorev gorunurlugunu kaydet.
2. [P1][owner: integrations] Recon contact icin gercek sensor/AI adapter sozlesmesini ve test fixture'larini hazirla.
3. [P1][owner: ops/ui] Operator station kurulum, gorev kabul/red/tamamla ve gun sonu rapor adimlarini saha proseduru olarak dondur.

# Secret Rotation Runbook

Bu dokuman, `Friend Drone MVP` icin kritik gizli degerlerin periyodik olarak nasil dondurulecegini tanimlar.

## Kapsam

- `JWT_SECRET_KEY`
- `BRIDGE_SOURCE_TOKEN`
- `MASTER_KEY`
- `BOOTSTRAP_ADMIN_PASSWORD`

## On Hazirlik

1. Uygulama trafiginin dusuk oldugu bir bakim penceresi sec.
2. Mevcut `.env` dosyasinin yedegini al.
3. Operasyon ekibi tarafindan yeni degerlerin guclu oldugu dogrulansin.

## 1) Yeni Secret Uretimi

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\generate_secrets.ps1
```

Script guclu yeni degerleri ekrana yazar. Bu degerleri guvenli bir sekilde `.env` dosyasina tasiyin.

## 2) Secret Kontrolu

`.env` dosyasini dogrula:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate_env_secrets.ps1 -EnvPath .env
```

Basarisiz cikarsa script hata kodu ile durur ve zayif/eksik alanlari listeler.

## 3) Rollout Sirasi

1. `.env` guncelle.
2. Servisleri yeniden baslat:

```powershell
docker compose up -d --build api bridge
```

3. Saglik kontrolu:
   - `http://localhost:8000/docs`
   - `http://localhost:8100/bridge/v1/health`
4. Login ve ingest smoke testi:
   - `POST /v1/auth/login`
   - `POST /bridge/v1/telemetry/ingest`

## 4) Bootstrap Admin Parola Rotasyonu

1. `.env` icinde `BOOTSTRAP_ADMIN_PASSWORD` degerini yeni bir degerle degistir.
2. Servisi yeniden baslat.
3. Bootstrap admin ilk login sonrasi zorunlu parola degistirme akisini tamamla (`/ui/change-password` veya `POST /v1/auth/change-password`).

## 5) Rollback

1. Son calisan `.env` yedegini geri koy.
2. `docker compose up -d --build api bridge` komutunu yeniden calistir.
3. `docs/HANDOFF_LOG.md` icine olay kaydi dus.

## Operasyon Notlari

- Secret degerleri loglara yazma.
- Secret paylasimini sohbet/issue yerine gizli kasa (vault/password manager) ile yap.
- Rotation periyodu onerisi:
  - `BRIDGE_SOURCE_TOKEN`: 30-60 gun
  - `JWT_SECRET_KEY`: 60-90 gun
  - `MASTER_KEY`: planli kesinti penceresi ile daha seyrek (veri etkisini analiz ederek)

# VPN + mTLS E2E Checklist

Bu checklist, Jetson -> Bridge -> API hattini sahada hizli ve tekrar edilebilir sekilde dogrulamak icindir.

## Amac

- VPN uzerinden bridge erisiminin calistigini dogrulamak.
- mTLS + bridge token + imzali telemetry zincirinin beklenen sonucu urettigini kanitlamak.
- Replay korumasinin aktif oldugunu gostermek.
- Opsiyonel `X-Device-Id` akisinda device health guncellemesini dogrulamak.

## On Kosullar

1. `docker compose up -d --build` ile servisler ayakta.
2. `powershell -ExecutionPolicy Bypass -File .\scripts\preflight_check.ps1 -EnvPath .env` basarili.
3. WireGuard baglantisi aktif (sahada).
4. mTLS ingress (NGINX) aktif ise bridge URL `https://...` olmali.
5. Bootstrap admin daha once parola degistirmedi ise scriptte `--allow-bootstrap-password-change` kullanilmali.

## Otomatik Smoke Script

Lab/iceride minimum komut:

```powershell
python .\scripts\vpn_mtls_e2e_smoke.py `
  --api-base-url http://localhost:8000 `
  --bridge-url http://localhost:8100 `
  --bridge-token "<bridge_token>" `
  --device-id "JETSON-PILOT-001" `
  --allow-bootstrap-password-change
```

Saha (VPN + mTLS) varyanti:

```powershell
python .\scripts\vpn_mtls_e2e_smoke.py `
  --api-base-url http://localhost:8000 `
  --bridge-url https://bridge-secure.local `
  --bridge-token "<bridge_token>" `
  --device-id "JETSON-PILOT-001" `
  --allow-bootstrap-password-change `
  --tls-ca-file C:\certs\ca.crt `
  --tls-client-cert-file C:\certs\jetson.crt `
  --tls-client-key-file C:\certs\jetson.key
```

Dry-run (konfig kontrolu):

```powershell
python .\scripts\vpn_mtls_e2e_smoke.py --dry-run
```

Not:

- Self-signed lab test icin gecici olarak `--tls-insecure-skip-verify` verilebilir.
- Operasyonel ortamda bu flag kullanilmamali.

## Beklenen Sonuclar

1. `Bridge health ok`
2. `Login ok`
3. `Drone and mission ready`
4. (Device-id verildiyse) `Device provisioned`
5. `Bridge ingest AUTHORIZED`
6. `Replay detection ok`
7. `Invalid token blocked (401)`
8. `Summary updated`
9. (Device-id verildiyse) `Device health updated`
10. Son satir: `[DONE] VPN+mTLS E2E smoke completed successfully`

## Basarisizlik Durumunda Hizli Triage

1. `Bridge health` fail:
   - `docker compose logs bridge --tail=100`
   - WireGuard route/peer durumu
2. Login fail:
   - Kullanici/parola
   - Zorunlu parola degisimi gereksinimi
3. Ingest fail:
   - Bridge token
   - Saat senkronu (clock skew)
   - Imza hesaplama (UID, ts, nonce, body hash)
4. Device fail:
   - `GET /v2/devices/{device_id}/health`
   - `X-Device-Id` header'in bridge tarafindan pass edildigini dogrula

## Operasyon Kaydi

Her smoke calistirmasi sonrasi:

1. `docs/HANDOFF_LOG.md` kaydi gir.
2. Kullanilan bridge URL/profili (lab veya vpn+mtls) not et.
3. Basarisizlik varsa incident/ticket referansi ekle.


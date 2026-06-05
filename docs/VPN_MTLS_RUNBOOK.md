# VPN + mTLS Runbook (Bridge/API Hatti)

Bu runbook, Jetson -> Bridge -> API hatti icin asagidaki guvenlik modelini standartlastirir:

- Trafik sadece VPN (WireGuard) uzerinden tasinir.
- Bridge public'te acik olmaz; sadece VPN segmentinden erisilir.
- HTTPS/mTLS ile istemci sertifikasi dogrulanir.
- Edge Agent tarafinda server CA dogrulamasi ve opsiyonel client cert/key kullanilir.

## 1) Hedef Topoloji

- Jetson Nano (edge agent)
  - WireGuard client
  - edge_agent (TLS enabled)
- Base network
  - WireGuard server
  - NGINX (mTLS reverse proxy)
  - Bridge service (`http://bridge:8100`)
  - API, Postgres, Redis (ic ag)

Akis:

1. Jetson telemetry uretir ve imzalar.
2. Packet `https://bridge-secure.local/bridge/v1/telemetry/ingest` adresine gider.
3. NGINX istemci cert dogrular, istegi Bridge'e aktarir.
4. Bridge pass-through signed olarak API ingest'e iletir.

## 2) WireGuard Kurulum Ozet Akis

Referans dosyalar:

- `deploy/security/wireguard/server-wg0.conf.example`
- `deploy/security/wireguard/jetson-wg0.conf.example`

Adimlar:

1. Sunucuda private/public key uret.
2. Jetson'da private/public key uret.
3. Sunucu `wg0.conf` icine Jetson peer ekle.
4. Jetson `wg0.conf` icine sunucu peer ekle.
5. Her iki tarafta WireGuard servisini baslat.
6. Ping ve route dogrulamasi yap (`10.44.0.0/24` gibi).

## 3) mTLS Sertifika Zinciri

Referans reverse proxy:

- `deploy/security/bridge-nginx-mtls.conf.example`

Ozet:

1. Internal CA uret.
2. Bridge ingress icin server cert uret (`bridge-secure.local` SAN ile).
3. Jetson cihazlari icin client cert uret (cihaz bazli CN).
4. NGINX'te:
   - `ssl_client_certificate` ile CA tanimla
   - `ssl_verify_client on` yap
5. Jetson edge agent'ta:
   - `--tls-ca-file /etc/friend-drone/certs/ca.crt`
   - `--tls-client-cert-file /etc/friend-drone/certs/client.crt`
   - `--tls-client-key-file /etc/friend-drone/certs/client.key`

## 4) Uygulama Konfigurasyon Kurallari

1. Bridge token zorunlu kalir (`X-Bridge-Token`).
2. `--tls-insecure-skip-verify` uretimde kullanilmaz.
3. Cert/key dosyalari root-only izinle tutulur (`600`).
4. Cert rotasyonunda eski cert grace period ile kaldirilir.
5. Tüm endpointler UTC timestamp ve audit zinciriyle calisir.

## 5) Operasyonel Dogrulama Checklist

1. VPN down iken Jetson -> Bridge erisimi yok.
2. VPN up + mTLS cert dogru iken ingest basarili.
3. mTLS cert hatali iken 4xx/handshake reject aliniyor.
4. Bridge token yanlis iken `401 Invalid bridge token`.
5. Edge spool retry davranisi beklenen sekilde calisiyor.
6. UI'da track/alarm akisi etkilenmeden devam ediyor.

## 6) Incident / Rollback

1. mTLS sorunu durumunda once cert chain dogrula (CA/server/client).
2. Gerekirse NGINX config rollback ile bir onceki stabil profile don.
3. Kesinti suresince edge spool birikir; baglanti duzelince replay olur.
4. Rollback sonrasi dead-letter ve outbox sayilari kontrol edilir.

## 7) Bu Paketten Sonraki Adim

1. Jetson sahada boot persistence + watchdog testini calistir.
2. VPN + mTLS e2e testini CI/disaster drill ile standartlastir.
3. Device lifecycle endpointleri (`provision/rotate/health`) backlog'a alin.


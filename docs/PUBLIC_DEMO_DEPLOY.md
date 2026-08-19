# Herkese Acik Demo Dagitimi (Render)

Amac: linke tiklayan kisi hicbir kurulum yapmadan, kendi tarayicisinda
`https://<servis>.onrender.com/ui/login` ekranini gorsun; iceriye ise yalnizca
paylastigin kullanici adi/sifre ile girebilsin.

## Neler Yayinlanir

| Bilesen | Durum | Neden |
| --- | --- | --- |
| `api` (FastAPI + `/ui/*`) | Yayinlanir | Demonun tamami bu servistedir |
| `postgres` | Yayinlanir (Render free) | Kalici veri |
| `redis` | Yayinlanmaz | Nonce store Redis yoksa bellege duser (`app/services/nonce_store.py`) |
| `bridge` | Yayinlanmaz | Saha telemetrisi icindir, demoda gereksiz |
| `edge_agent` | Yayinlanmaz | Jetson uzerinde calisan saha bileseni |

Kod PostGIS'e ozgu hicbir tip/fonksiyon kullanmadigi icin duz PostgreSQL yeterlidir.

## Guvenlik Modeli

- `/ui/*` ve `/v1/*`, `/v2/*` uclarinin tamami kimlik dogrulamasi ister.
  Kimliksiz erisilebilen tek uclar: `GET/POST /ui/login`, `POST /v1/auth/login`
  ve HMAC imzali `POST /v1/telemetry/ingest`.
- `ENVIRONMENT=prod` dogrulamasi zayif yapilandirmayi engeller: JWT anahtari en az
  32 karakter, `MASTER_KEY` gecerli Fernet anahtari, admin sifresi en az 12 karakter,
  `SECURE_COOKIES=true`, `CORS_ORIGINS` icinde `*` yasak (`app/config.py`).
- **Hicbir kimlik bilgisi repoya veya README'ye yazilmaz.** Tum sirlar Render
  panelinden girilir; `render.yaml` yalnizca "panelden doldurulacak" isaretini tutar.
- Repodaki `.env.example` degerleri yalnizca yerel gelistirme icindir; canli demoda
  kullanilmaz.

## Kurulum

### 1. Sirlari uret

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Ciktiyi `MASTER_KEY` olarak sakla. Admin sifresi icin en az 12 karakterli,
`.env.example` icindekilerden farkli bir deger belirle.

### 2. Blueprint'i olustur

1. <https://dashboard.render.com/blueprints> -> **New Blueprint Instance**
2. `EgeOzdemirr/DroneHavaSahasi` reposunu sec (Render'a GitHub erisimi ver).
3. Render `render.yaml` dosyasini okur ve `sync: false` isaretli degiskenleri sorar:

   | Degisken | Deger |
   | --- | --- |
   | `MASTER_KEY` | 1. adimda uretilen Fernet anahtari |
   | `BOOTSTRAP_ADMIN_USERNAME` | ornegin `komutan` (`admin` kullanma) |
   | `BOOTSTRAP_ADMIN_PASSWORD` | en az 12 karakterli guclu sifre |

4. **Apply** de. Ilk imaj derlemesi yaklasik 5-10 dakika surer.

`JWT_SECRET_KEY` Render tarafindan rastgele uretilir, elle girilmez.

### 3. URL'i dogrula

Deploy bitince servisin gercek adresini kontrol et. `hava-sahasi-demo` adi baska bir
hesapta kullanildiysa Render sonuna ek getirir. Adres farkliysa servis ->
**Environment** -> `CORS_ORIGINS` degerini gercek adresle guncelle ve yeniden deploy et:

```
["https://<gercek-adres>.onrender.com"]
```

Bu adim atlanirsa uygulama `prod` dogrulamasi yuzunden acilmaz.

### 4. Ilk giris ve sifre kilitleme

Bootstrap admin `must_change_password=True` ile olusur (`app/services/bootstrap.py`).
Bu yuzden **demoyu paylasmadan once sen gir**:

1. `https://<adres>/ui/login`
2. Adim 2'deki kullanici adi/sifre ile giris yap.
3. Zorunlu sifre degistirme ekraninda kalici demo sifresini belirle.
4. Artik yalnizca bu son sifreyi paylas.

Bu adim atlanirsa, linki acan ilk kisi sifreyi degistirmek zorunda kalir ve
kontrolu eline alir.

### 5. Demo senaryosu

Kontrol merkezindeki `Sunum Akisi` paneli ile: reset -> senaryo yukle -> hedef
olustur -> operator panelinden gorevi kabul et. Ayrintilar README'deki
"Decision-Maker Demo" bolumunde.

Senaryo yukleme `demo_operator_1..3 / ***REMOVED***` hesaplarini olusturur ve bu
sifreler README'de yazilidir. Demoyu tanimadigin kisilere aciyorsan senaryoyu
sunumdan sonra `Reset` ile temizle veya bu hesaplarin sifresini degistir.

## Ucretsiz Plan Sinirlari

- **Uyku modu:** servis 15 dakika istek almazsa uyur; sonraki ilk istek 50 saniyeye
  kadar surebilir. Sunumdan birkac dakika once linki bir kez ac.
- **Veritabani omru:** Render'in ucretsiz PostgreSQL ornekleri olusturuldiktan 30 gun
  sonra silinir. Kalici demo icin ucretsiz ve suresiz bir Postgres (ornegin Neon)
  baglanti dizesini `DATABASE_URL` olarak elle gir ve `render.yaml` icindeki
  `databases:` blogunu kaldir. Baslatma betigi `postgres://` / `postgresql://`
  semalarini otomatik cevirir, ek duzenleme gerekmez.
- **Bellek:** ucretsiz orneklerde 512 MB. Tek uvicorn worker'i yeterlidir.
- **Dis servisler:** harita karolari (OpenFreeMap/unpkg) ve OpenSky ucusları
  ziyaretcinin tarayicisindan/sunucudan cekilir; bu servisler kapali oldugunda
  harita bos gorunebilir. Tamamen cevrimdisi harita icin `MAP_PROVIDER=offline`.

## Guncelleme

`main` dalina push edildiginde Render otomatik yeniden deploy eder
(`autoDeploy: true`). Yeni migrasyonlar acilista `alembic upgrade head` ile uygulanir.

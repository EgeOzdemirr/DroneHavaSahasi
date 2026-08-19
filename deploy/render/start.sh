#!/bin/sh
# Render (ve benzeri PaaS) uzerinde tek servislik demo baslatici.
# - Saglayici baglanti dizesini SQLAlchemy 2.x'in bekledigi surucu semasina cevirir
# - Sema migrasyonlarini uygular
# - Uygulamayi saglayicinin verdigi $PORT uzerinde, ters proxy arkasinda baslatir
set -e

case "${DATABASE_URL:-}" in
  postgres://*)   DATABASE_URL="postgresql+psycopg2://${DATABASE_URL#postgres://}" ;;
  postgresql://*) DATABASE_URL="postgresql+psycopg2://${DATABASE_URL#postgresql://}" ;;
esac
export DATABASE_URL

alembic upgrade head

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"

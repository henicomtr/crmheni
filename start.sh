#!/bin/sh
# Container başlangıç scripti: migration çalıştır, sonra uygulamayı başlat

set -e

echo "⏳ Veritabanı migration'ları uygulanıyor..."
alembic upgrade head

echo "🚀 Uygulama başlatılıyor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"

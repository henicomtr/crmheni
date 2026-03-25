FROM python:3.11-slim

# Çalışma dizini
WORKDIR /app

# Sistem bağımlılıkları (psycopg binary için libpq gerekli)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python bağımlılıklarını kur (önce kopyala — Docker layer cache kazanımı)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyalarını kopyala
COPY . .

# Statik dosyalar için upload klasörünü oluştur
RUN mkdir -p static/upload

# Startup scriptini çalıştırılabilir yap
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]

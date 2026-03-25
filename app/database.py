import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Ortam değişkeninden DATABASE_URL oku; yoksa SQLite'a düş (local geliştirme)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./heni.db")
# DATABASE_URL'i otomatik düzelt (psycopg3 uyumluluğu)
# Coolify ve bazı provider'lar postgres:// prefix'i verebilir
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# PostgreSQL ve SQLite için ayrı engine ayarları
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,         # Havuzda hazır bekleyen bağlantı sayısı
        max_overflow=20,      # Havuz dolunca açılabilecek ek bağlantı
        pool_pre_ping=True,   # Kopuk bağlantıları kullanmadan önce test et
    )
else:
    # SQLite — local geliştirme için
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

from fastapi import Depends
from sqlalchemy.orm import Session

def get_db():
    # Her istek için yeni DB oturumu aç, bittikten sonra kapat
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
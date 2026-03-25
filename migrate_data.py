"""
SQLite → PostgreSQL Veri Taşıma Scripti
Kullanım:
    1. .env dosyasında DATABASE_URL=postgresql://... olarak ayarla
    2. python migrate_data.py
"""

import os
import sys
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Bağlantı kurulumu ───────────────────────────────────────────────
SQLITE_PATH = "heni.db"
PG_URL = os.getenv("DATABASE_URL")

if not PG_URL or not (PG_URL.startswith("postgresql") or PG_URL.startswith("postgres")):
    print("❌ HATA: .env dosyasında DATABASE_URL postgresql:// ile başlamalı")
    sys.exit(1)

# psycopg3 uyumluluğu — Coolify postgres://, standart postgresql:// prefix'ini düzelt
if PG_URL.startswith("postgres://"):
    PG_URL = PG_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif PG_URL.startswith("postgresql://"):
    PG_URL = PG_URL.replace("postgresql://", "postgresql+psycopg://", 1)

print(f"📂 SQLite: {SQLITE_PATH}")
print(f"🐘 PostgreSQL: {PG_URL.split('@')[-1]}")  # şifreyi gizle

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

sqlite_engine = create_engine(f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False})
pg_engine     = create_engine(PG_URL, pool_pre_ping=True)

SqliteSession = sessionmaker(bind=sqlite_engine)
PgSession     = sessionmaker(bind=pg_engine)

def get_rows(sqlite_conn, table: str) -> list[dict]:
    """SQLite tablosundan tüm satırları dict listesi olarak çeker."""
    try:
        result = sqlite_conn.execute(text(f"SELECT * FROM {table}"))
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in result.fetchall()]
    except Exception as e:
        print(f"  ⚠️  {table} okunamadı: {e}")
        return []

def insert_rows(pg_conn, table: str, rows: list[dict]):
    """Satırları PostgreSQL tablosuna ekler, çakışmaları atlar."""
    if not rows:
        print(f"  ⏭️  {table}: boş, atlanıyor")
        return

    inserted = 0
    skipped  = 0
    for row in rows:
        # None olmayan kolonları al
        cols = [k for k, v in row.items() if v is not None]
        if not cols:
            continue
        placeholders = ", ".join([f":{c}" for c in cols])
        col_names    = ", ".join(cols)
        sql = text(f"""
            INSERT INTO {table} ({col_names})
            VALUES ({placeholders})
            ON CONFLICT DO NOTHING
        """)
        try:
            pg_conn.execute(sql, {k: row[k] for k in cols})
            inserted += 1
        except Exception as e:
            skipped += 1
            if skipped <= 3:  # İlk 3 hatayı göster
                print(f"    ⚠️  Satır atlandı: {e}")
    pg_conn.commit()
    print(f"  ✅ {table}: {inserted} eklendi, {skipped} atlandı")

# Taşınacak tablolar — foreign key sırasına göre sıralı
TABLES = [
    "users",
    "products",
    "product_translations",
    "customers",
    "suppliers",
    "quote_requests",
    "messages",
    "leads",
    "orders",
    "finance",
    "account_transactions",
    "pages",
    "page_translations",
    "faq_items",
    "category_contents",
    "category_translations",
    "category_faqs",
    "homepage_contents",
    "site_settings",
]

def main():
    print("\n🚀 Veri taşıma başlıyor...\n")

    sqlite_conn = sqlite_engine.connect()
    pg_conn     = pg_engine.connect()

    # PostgreSQL'deki mevcut tablo listesini kontrol et
    insp = inspect(pg_engine)
    pg_tables = insp.get_table_names()
    print(f"🐘 PostgreSQL'de {len(pg_tables)} tablo bulundu\n")

    total_rows = 0
    for table in TABLES:
        if table not in pg_tables:
            print(f"  ❌ {table}: PostgreSQL'de bulunamadı, migration çalıştırıldı mı?")
            continue

        rows = get_rows(sqlite_conn, table)
        print(f"📋 {table}: {len(rows)} satır bulundu")
        insert_rows(pg_conn, table, rows)
        total_rows += len(rows)

    sqlite_conn.close()
    pg_conn.close()

    print(f"\n✅ Tamamlandı! Toplam {total_rows} satır işlendi.")
    print("\n⚠️  Sequence'ları güncellemeyi unutma:")
    print("   python migrate_data.py --fix-sequences\n")

def fix_sequences():
    """
    PostgreSQL sequence'larını taşınan veriye göre günceller.
    Veri taşıma sonrası yeni kayıt eklenirken ID çakışmasını önler.
    """
    print("\n🔧 Sequence'lar güncelleniyor...\n")
    with pg_engine.connect() as conn:
        for table in TABLES:
            try:
                result = conn.execute(text(f"SELECT MAX(id) FROM {table}"))
                max_id = result.scalar()
                if max_id:
                    conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), {max_id})"
                    ))
                    print(f"  ✅ {table}: sequence {max_id}'e ayarlandı")
            except Exception as e:
                print(f"  ⚠️  {table}: {e}")
        conn.commit()
    print("\n✅ Sequence güncelleme tamamlandı!")

if __name__ == "__main__":
    if "--fix-sequences" in sys.argv:
        fix_sequences()
    else:
        main()
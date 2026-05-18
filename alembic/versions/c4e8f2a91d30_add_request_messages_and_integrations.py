"""add_request_messages_and_integrations

Revision ID: c4e8f2a91d30
Revises: 3f16dc2e5fdd
Create Date: 2026-05-18

"""
from alembic import op
import sqlalchemy as sa

revision = 'c4e8f2a91d30'
down_revision = '3f16dc2e5fdd'
branch_labels = None
depends_on = None


def upgrade():
    # quote_requests: is_read kolonunu INTEGER'dan BOOLEAN'a çevir (veya BOOLEAN olarak ekle)
    op.execute("""
        DO $$
        DECLARE col_type TEXT;
        BEGIN
            SELECT data_type INTO col_type
            FROM information_schema.columns
            WHERE table_name = 'quote_requests' AND column_name = 'is_read';

            IF col_type IS NULL THEN
                ALTER TABLE quote_requests ADD COLUMN is_read BOOLEAN DEFAULT FALSE;
            ELSIF col_type = 'integer' THEN
                -- Önce default'u kaldır (integer default boolean'a otomatik cast edilemez)
                ALTER TABLE quote_requests ALTER COLUMN is_read DROP DEFAULT;
                ALTER TABLE quote_requests
                    ALTER COLUMN is_read TYPE BOOLEAN USING is_read::BOOLEAN;
                ALTER TABLE quote_requests ALTER COLUMN is_read SET DEFAULT FALSE;
            END IF;
        END $$;
    """)

    # quote_requests: last_contacted_at kolonu ekle
    op.execute("""
        ALTER TABLE quote_requests
        ADD COLUMN IF NOT EXISTS last_contacted_at TIMESTAMP
    """)

    # request_messages tablosunu oluştur
    op.execute("""
        CREATE TABLE IF NOT EXISTS request_messages (
            id         SERIAL PRIMARY KEY,
            request_id INTEGER NOT NULL REFERENCES quote_requests(id) ON DELETE CASCADE,
            channel    VARCHAR(20) NOT NULL,
            content    TEXT NOT NULL,
            admin_name VARCHAR,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_request_messages_request_id
        ON request_messages(request_id)
    """)

    # site_settings: SMTP kolonları ekle
    op.execute("""
        ALTER TABLE site_settings
        ADD COLUMN IF NOT EXISTS smtp_host VARCHAR
    """)
    op.execute("""
        ALTER TABLE site_settings
        ADD COLUMN IF NOT EXISTS smtp_port INTEGER
    """)
    op.execute("""
        ALTER TABLE site_settings
        ADD COLUMN IF NOT EXISTS smtp_user VARCHAR
    """)
    op.execute("""
        ALTER TABLE site_settings
        ADD COLUMN IF NOT EXISTS smtp_password VARCHAR
    """)
    op.execute("""
        ALTER TABLE site_settings
        ADD COLUMN IF NOT EXISTS smtp_from_email VARCHAR
    """)

    # site_settings: Evolution API (WhatsApp) kolonları ekle
    op.execute("""
        ALTER TABLE site_settings
        ADD COLUMN IF NOT EXISTS evolution_api_url VARCHAR
    """)
    op.execute("""
        ALTER TABLE site_settings
        ADD COLUMN IF NOT EXISTS evolution_api_key VARCHAR
    """)
    op.execute("""
        ALTER TABLE site_settings
        ADD COLUMN IF NOT EXISTS evolution_instance VARCHAR
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS request_messages")
    op.execute("ALTER TABLE quote_requests DROP COLUMN IF EXISTS last_contacted_at")
    op.execute("ALTER TABLE quote_requests DROP COLUMN IF EXISTS is_read")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS smtp_host")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS smtp_port")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS smtp_user")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS smtp_password")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS smtp_from_email")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS evolution_api_url")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS evolution_api_key")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS evolution_instance")

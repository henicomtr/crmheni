"""add_service_page_contents

Revision ID: 3f16dc2e5fdd
Revises: 3f7d069f046e
Create Date: 2026-05-08

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3f16dc2e5fdd'
down_revision = '3f7d069f046e'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS service_page_contents (
            id SERIAL PRIMARY KEY,
            slug VARCHAR(32) NOT NULL,
            lang VARCHAR(5) NOT NULL,
            data TEXT,
            updated_at TIMESTAMP,
            CONSTRAINT uq_service_page_slug_lang UNIQUE (slug, lang)
        )
    """)
    # Tablo zaten varsa (manuel oluşturulduysa) updated_at kolonunu ekle
    op.execute("""
        ALTER TABLE service_page_contents
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP
    """)


def downgrade():
    op.drop_table('service_page_contents')
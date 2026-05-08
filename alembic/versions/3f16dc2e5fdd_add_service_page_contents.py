def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS service_page_contents (
            id SERIAL PRIMARY KEY,
            slug VARCHAR NOT NULL,
            lang VARCHAR NOT NULL,
            data TEXT,
            CONSTRAINT uq_service_page_slug_lang UNIQUE (slug, lang)
        )
    """)

def downgrade():
    op.drop_table('service_page_contents')
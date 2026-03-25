"""initial_schema

Revision ID: 3f7d069f046e
Revises:
Create Date: 2025-03-25

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '3f7d069f046e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(), unique=True, nullable=True),
        sa.Column('password', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=True),
    )

    # ── products ───────────────────────────────────────────────────────
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('unit_price', sa.Float(), nullable=True),
        sa.Column('stock', sa.Integer(), nullable=True),
        sa.Column('barcode', sa.String(), nullable=True),
        sa.Column('rating', sa.Float(), default=5.0),
        sa.Column('image', sa.String(), nullable=True),
        sa.Column('product_video', sa.String(), nullable=True),
        sa.Column('loading_video', sa.String(), nullable=True),
        sa.Column('msds', sa.String(), nullable=True),
        sa.Column('tds', sa.String(), nullable=True),
        sa.Column('analysis_doc', sa.String(), nullable=True),
        sa.Column('quality_doc', sa.String(), nullable=True),
        sa.Column('export_countries', sa.String(), nullable=True),
        sa.Column('slug', sa.String(), unique=True, index=True, nullable=True),
        sa.Column('pieces_per_box', sa.Integer(), default=1),
        sa.Column('boxes_per_pallet', sa.Integer(), default=1),
        sa.Column('min_pallet_order', sa.Integer(), default=1),
        sa.Column('pallets_20ft', sa.Integer(), default=10),
        sa.Column('pallets_40ft', sa.Integer(), default=20),
        sa.Column('discount_1_pallet', sa.Float(), default=0.0),
        sa.Column('discount_2_pallet', sa.Float(), default=0.0),
        sa.Column('discount_3_pallet', sa.Float(), default=0.0),
        sa.Column('discount_4_pallet', sa.Float(), default=0.0),
        sa.Column('discount_5_plus_pallet', sa.Float(), default=0.0),
    )

    # ── product_translations ───────────────────────────────────────────
    op.create_table(
        'product_translations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('lang', sa.String(5), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=True, index=True),
        sa.Column('short_description', sa.String(), nullable=True),
        sa.Column('long_description', sa.Text(), nullable=True),
        sa.Column('meta_title', sa.String(), nullable=True),
        sa.Column('meta_description', sa.String(), nullable=True),
        sa.UniqueConstraint('product_id', 'lang', name='uq_product_lang'),
    )

    # ── quote_requests ─────────────────────────────────────────────────
    op.create_table(
        'quote_requests',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('company_name', sa.String(), nullable=False),
        sa.Column('contact_person', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('total_price', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), default='USD'),
        sa.Column('cart_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── messages ───────────────────────────────────────────────────────
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sender', sa.String(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # ── customers ──────────────────────────────────────────────────────
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('contact_person', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # ── suppliers ──────────────────────────────────────────────────────
    op.create_table(
        'suppliers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('contact_person', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('tax_id', sa.String(), nullable=True),
        sa.Column('billing_address', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('district', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # ── leads ──────────────────────────────────────────────────────────
    op.create_table(
        'leads',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('converted_to_customer', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # ── orders ─────────────────────────────────────────────────────────
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # ── finance ────────────────────────────────────────────────────────
    op.create_table(
        'finance',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), default='TRY'),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('reference_no', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('account_source', sa.String(), default='official', nullable=False),
        sa.Column('is_transfer', sa.Integer(), default=0),
        sa.Column('transfer_pair_id', sa.Integer(), nullable=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('transaction_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # ── account_transactions ───────────────────────────────────────────
    op.create_table(
        'account_transactions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), default='USD'),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('reference_no', sa.String(), nullable=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id', ondelete='CASCADE'), nullable=True),
        sa.Column('finance_transaction_id', sa.Integer(), sa.ForeignKey('finance.id', ondelete='SET NULL'), nullable=True),
        sa.Column('transaction_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # ── pages ──────────────────────────────────────────────────────────
    op.create_table(
        'pages',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('slug', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('template', sa.String(), default='page_generic.html'),
        sa.Column('is_published', sa.Integer(), default=1),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.Column('show_in_nav', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # ── page_translations ──────────────────────────────────────────────
    op.create_table(
        'page_translations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('page_id', sa.Integer(), sa.ForeignKey('pages.id'), nullable=False),
        sa.Column('lang', sa.String(5), nullable=False),
        sa.Column('slug', sa.String(), nullable=True, index=True),
        sa.Column('title', sa.String(), nullable=False, default=''),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('meta_title', sa.String(), nullable=True),
        sa.Column('meta_description', sa.String(), nullable=True),
        sa.Column('og_title', sa.String(), nullable=True),
        sa.Column('og_description', sa.String(), nullable=True),
        sa.UniqueConstraint('page_id', 'lang', name='uq_page_lang'),
    )

    # ── faq_items ──────────────────────────────────────────────────────
    op.create_table(
        'faq_items',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('page_id', sa.Integer(), sa.ForeignKey('pages.id'), nullable=False),
        sa.Column('lang', sa.String(5), nullable=False),
        sa.Column('question', sa.String(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.UniqueConstraint('page_id', 'lang', 'sort_order', name='uq_faq_page_lang_order'),
    )

    # ── category_contents ──────────────────────────────────────────────
    op.create_table(
        'category_contents',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('category_key', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('category_slug', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('is_published', sa.Integer(), default=1),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # ── category_translations ──────────────────────────────────────────
    op.create_table(
        'category_translations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('category_contents.id'), nullable=False),
        sa.Column('lang', sa.String(5), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('intro', sa.Text(), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('meta_title', sa.String(), nullable=True),
        sa.Column('meta_description', sa.String(), nullable=True),
        sa.Column('og_title', sa.String(), nullable=True),
        sa.Column('og_description', sa.String(), nullable=True),
        sa.UniqueConstraint('category_id', 'lang', name='uq_cat_lang'),
    )

    # ── category_faqs ──────────────────────────────────────────────────
    op.create_table(
        'category_faqs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('category_contents.id'), nullable=False),
        sa.Column('lang', sa.String(5), nullable=False),
        sa.Column('question', sa.String(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.UniqueConstraint('category_id', 'lang', 'sort_order', name='uq_catfaq_lang_order'),
    )

    # ── homepage_contents ──────────────────────────────────────────────
    op.create_table(
        'homepage_contents',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('lang', sa.String(5), unique=True, nullable=False, index=True),
        sa.Column('data', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # ── site_settings ──────────────────────────────────────────────────
    op.create_table(
        'site_settings',
        sa.Column('id', sa.Integer(), primary_key=True, default=1),
        sa.Column('site_name', sa.String(), default='Heni'),
        sa.Column('logo_url', sa.String(), nullable=True),
        sa.Column('logo_white_url', sa.String(), nullable=True),
        sa.Column('favicon_url', sa.String(), nullable=True),
        sa.Column('contact_email', sa.String(), nullable=True),
        sa.Column('contact_phone', sa.String(), nullable=True),
        sa.Column('contact_address', sa.String(), nullable=True),
        sa.Column('social_linkedin', sa.String(), nullable=True),
        sa.Column('social_instagram', sa.String(), nullable=True),
        sa.Column('social_twitter', sa.String(), nullable=True),
        sa.Column('social_whatsapp', sa.String(), nullable=True),
        sa.Column('seo_title_template', sa.String(), nullable=True),
        sa.Column('seo_description', sa.String(), nullable=True),
        sa.Column('analytics_code', sa.Text(), nullable=True),
        sa.Column('custom_css', sa.Text(), nullable=True),
        sa.Column('footer_description', sa.Text(), nullable=True),
        sa.Column('footer_copyright_lead', sa.String(), nullable=True),
        sa.Column('footer_copyright', sa.String(), nullable=True),
        sa.Column('footer_columns', sa.Text(), nullable=True),
        sa.Column('footer_bg_image_url', sa.String(), nullable=True),
        sa.Column('i18n', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    # Tabloları ters sırada sil (foreign key bağımlılıkları için)
    op.drop_table('site_settings')
    op.drop_table('homepage_contents')
    op.drop_table('category_faqs')
    op.drop_table('category_translations')
    op.drop_table('category_contents')
    op.drop_table('faq_items')
    op.drop_table('page_translations')
    op.drop_table('pages')
    op.drop_table('account_transactions')
    op.drop_table('finance')
    op.drop_table('orders')
    op.drop_table('leads')
    op.drop_table('suppliers')
    op.drop_table('customers')
    op.drop_table('messages')
    op.drop_table('quote_requests')
    op.drop_table('product_translations')
    op.drop_table('products')
    op.drop_table('users')
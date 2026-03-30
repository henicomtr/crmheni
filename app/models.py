from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
from sqlalchemy.sql import func

SUPPORTED_LANGS = ["en", "tr", "de", "fr", "ar", "ru", "es"]
DEFAULT_LANG    = "en"


class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    email         = Column(String, unique=True)
    password      = Column(String)
    role          = Column(String)
    is_superadmin = Column(Boolean, default=False)
    permissions   = Column(Text, default="[]")  # JSON: ["urunler", "musteriler", ...]

    def get_permissions(self) -> list:
        """İzin listesini JSON'dan çözer."""
        import json
        try:
            return json.loads(self.permissions or "[]")
        except Exception:
            return []

    def has_permission(self, perm: str) -> bool:
        """Superadmin her şeye erişir; diğerleri izin listesine göre."""
        if self.is_superadmin:
            return True
        return perm in self.get_permissions()


class Product(Base):
    __tablename__ = "products"

    id               = Column(Integer, primary_key=True, index=True)
    category         = Column(String)
    unit_price       = Column(Float)
    stock            = Column(Integer)
    barcode          = Column(String)
    rating           = Column(Float, default=5.0)
    image            = Column(String)
    product_video    = Column(String)
    loading_video    = Column(String)
    msds             = Column(String)
    tds              = Column(String)
    analysis_doc     = Column(String)
    quality_doc      = Column(String)
    export_countries = Column(String)
    slug             = Column(String, unique=True, index=True)

    # Lojistik
    pieces_per_box         = Column(Integer, default=1)
    boxes_per_pallet       = Column(Integer, default=1)
    min_pallet_order       = Column(Integer, default=1)
    pallets_20ft           = Column(Integer, default=10)
    pallets_40ft           = Column(Integer, default=20)
    discount_1_pallet      = Column(Float, default=0.0)
    discount_2_pallet      = Column(Float, default=0.0)
    discount_3_pallet      = Column(Float, default=0.0)
    discount_4_pallet      = Column(Float, default=0.0)
    discount_5_plus_pallet = Column(Float, default=0.0)

    # Kullanıcı değerlendirme sayısı (ProductRating tablosundan hesaplanır)
    rating_count = Column(Integer, default=0)

    # Son güncelleme tarihi — sitemap lastmod ve cache invalidation için
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    translations = relationship(
        "ProductTranslation",
        back_populates="product",
        cascade="all, delete-orphan"
    )
    ratings = relationship(
        "ProductRating",
        back_populates="product",
        cascade="all, delete-orphan"
    )

    def get_translation(self, lang: str) -> "ProductTranslation":
        for t in self.translations:
            if t.lang == lang:
                return t
        for t in self.translations:
            if t.lang == DEFAULT_LANG:
                return t
        return self.translations[0] if self.translations else None


    def get_slug_for(self, lang: str) -> str:
        """Dile özgü slug: once translation.slug, yoksa Product.slug (EN fallback)."""
        t = self.get_translation(lang)
        if t and t.slug:
            return t.slug
        return self.slug or ""

    def calculate_discounted_price(self, pallets):
        tiers = [
            (5, self.discount_5_plus_pallet),
            (4, self.discount_4_pallet),
            (3, self.discount_3_pallet),
            (2, self.discount_2_pallet),
            (1, self.discount_1_pallet),
        ]
        for limit, disc in tiers:
            if pallets >= limit:
                return disc or 0.0
        return 0.0


class ProductTranslation(Base):
    __tablename__ = "product_translations"
    __table_args__ = (
        UniqueConstraint("product_id", "lang", name="uq_product_lang"),
    )

    id                = Column(Integer, primary_key=True, index=True)
    product_id        = Column(Integer, ForeignKey("products.id"), nullable=False)
    lang              = Column(String(5), nullable=False)
    name              = Column(String, nullable=False)
    slug              = Column(String, nullable=True, index=True)  # Dile özgü SEO slug
    short_description = Column(String)
    long_description  = Column(Text)
    meta_title        = Column(String)
    meta_description  = Column(String)

    product = relationship("Product", back_populates="translations")


class ProductRating(Base):
    """Tarayıcı başına bir kez oy kullanılan ürün değerlendirmesi."""
    __tablename__ = "product_ratings"
    __table_args__ = (
        UniqueConstraint("product_id", "browser_id", name="uq_rating_product_browser"),
    )

    id         = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    # Tarayıcıya özgü UUID — localStorage'da saklanır, sunucuya gönderilir
    browser_id = Column(String, nullable=False)
    # 1–5 arası tam sayı puan
    rating     = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="ratings")


class QuoteRequest(Base):
    __tablename__ = "quote_requests"
    id             = Column(Integer, primary_key=True, index=True)
    company_name   = Column(String, nullable=False)
    contact_person = Column(String, nullable=False)
    email          = Column(String, nullable=False)
    phone          = Column(String, nullable=True)
    country        = Column(String, nullable=True)
    total_price    = Column(Float, nullable=False)
    currency       = Column(String, default="USD")
    cart_data      = Column(Text, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    id         = Column(Integer, primary_key=True)
    sender     = Column(String)
    content    = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Customer(Base):
    __tablename__ = "customers"
    id             = Column(Integer, primary_key=True)
    name           = Column(String)
    country        = Column(String)
    email          = Column(String, nullable=True)
    phone          = Column(String, nullable=True)
    contact_person = Column(String, nullable=True)
    notes          = Column(String, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"
    id              = Column(Integer, primary_key=True)
    name            = Column(String, nullable=False)
    contact_person  = Column(String, nullable=True)
    email           = Column(String, nullable=True)
    phone           = Column(String, nullable=True)
    tax_id          = Column(String, nullable=True)
    billing_address = Column(String, nullable=True)
    city            = Column(String, nullable=True)
    district        = Column(String, nullable=True)
    notes           = Column(String, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)


class Lead(Base):
    __tablename__ = "leads"
    id                    = Column(Integer, primary_key=True)
    country               = Column(String)
    converted_to_customer = Column(Integer, default=0)
    created_at            = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id         = Column(Integer, primary_key=True)
    product_id = Column(Integer)
    quantity   = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class FinanceTransaction(Base):
    __tablename__ = "finance"
    id            = Column(Integer, primary_key=True)
    # "income" (gelir) veya "expense" (gider)
    type          = Column(String, nullable=False)
    amount        = Column(Float, nullable=False)
    currency      = Column(String, default="TRY")
    description   = Column(String, nullable=True)
    reference_no  = Column(String, nullable=True)    # fatura/fiş no
    # Kategori: kira, maaş, hammadde, satış, kargo, diğer...
    category      = Column(String, nullable=True)
    # Hesap kaynağı: "official" (şirket hesabı) veya "personal" (şahsi hesap/elden)
    account_source  = Column(String, default="official", nullable=False)
    # Transfer kayıtları
    is_transfer      = Column(Integer, default=0)
    transfer_pair_id = Column(Integer, nullable=True)
    # İlişkili taraf (biri dolu olur, diğeri boş)
    customer_id   = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    supplier_id   = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    # Tarih (manuel girilebilir, default = kayıt anı)
    transaction_date = Column(DateTime, default=datetime.utcnow)
    created_at    = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", foreign_keys=[customer_id])
    supplier = relationship("Supplier", foreign_keys=[supplier_id])


class AccountTransaction(Base):
    """
    Cari Hesap Hareketi - Müşteri ve Tedarikçilerle olan borç/alacak takibi
    """
    __tablename__ = "account_transactions"
    id               = Column(Integer, primary_key=True)
    # "debit" (borç - bize borçları) veya "credit" (alacak - bizim borçlarımız)
    type             = Column(String, nullable=False)
    amount           = Column(Float, nullable=False)
    currency         = Column(String, default="USD")
    description      = Column(String, nullable=True)  # ürün/hizmet açıklaması
    reference_no     = Column(String, nullable=True)  # fatura no
    # İlişkili taraf (biri dolu olur)
    customer_id      = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=True)
    supplier_id      = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True)
    # Finans kaydıyla ilişkilendirme (opsiyonel - ödeme yapıldığında)
    finance_transaction_id = Column(Integer, ForeignKey("finance.id", ondelete="SET NULL"), nullable=True)
    transaction_date = Column(DateTime, default=datetime.utcnow)
    created_at       = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", foreign_keys=[customer_id], backref="account_transactions")
    supplier = relationship("Supplier", foreign_keys=[supplier_id], backref="account_transactions")
    finance_transaction = relationship("FinanceTransaction", foreign_keys=[finance_transaction_id])


# ─────────────────────────────────────────────────────────────────────
# CMS — Sayfalar, FAQ ve Site Ayarları
# ─────────────────────────────────────────────────────────────────────

class Page(Base):
    """
    Site sayfaları (anasayfa, hakkımızda, iletişim, vb.)
    slug: her dil için ayrı slug PageTranslation.slug üzerinden tutulur;
    bu alan EN için master slug'dır.
    """
    __tablename__ = "pages"

    id           = Column(Integer, primary_key=True, index=True)
    slug         = Column(String, unique=True, index=True, nullable=False)  # EN master slug
    template     = Column(String, default="page_generic.html")              # hangi Jinja2 şablonu
    is_published = Column(Integer, default=1)                               # 1=yayında, 0=taslak
    sort_order   = Column(Integer, default=0)
    show_in_nav  = Column(Integer, default=0)                               # navbar'da göster
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    translations = relationship(
        "PageTranslation",
        back_populates="page",
        cascade="all, delete-orphan",
    )
    faqs = relationship(
        "FaqItem",
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="FaqItem.sort_order",
    )

    def get_translation(self, lang: str) -> "PageTranslation":
        for t in self.translations:
            if t.lang == lang:
                return t
        for t in self.translations:
            if t.lang == DEFAULT_LANG:
                return t
        return self.translations[0] if self.translations else None

    def get_slug_for(self, lang: str) -> str:
        t = self.get_translation(lang)
        if t and t.slug:
            return t.slug
        return self.slug or ""


class PageTranslation(Base):
    """Her sayfa × dil kombinasyonu için içerik ve SEO alanları."""
    __tablename__ = "page_translations"
    __table_args__ = (
        UniqueConstraint("page_id", "lang", name="uq_page_lang"),
    )

    id               = Column(Integer, primary_key=True, index=True)
    page_id          = Column(Integer, ForeignKey("pages.id"), nullable=False)
    lang             = Column(String(5), nullable=False)
    slug             = Column(String, nullable=True, index=True)   # dile özgü SEO slug
    title            = Column(String, nullable=False, default="")
    body             = Column(Text, nullable=True)                  # HTML içerik
    meta_title       = Column(String, nullable=True)
    meta_description = Column(String, nullable=True)
    og_title         = Column(String, nullable=True)
    og_description   = Column(String, nullable=True)

    page = relationship("Page", back_populates="translations")


class FaqItem(Base):
    """Sayfa başına, dil başına SSS sorusu."""
    __tablename__ = "faq_items"
    __table_args__ = (
        UniqueConstraint("page_id", "lang", "sort_order", name="uq_faq_page_lang_order"),
    )

    id         = Column(Integer, primary_key=True, index=True)
    page_id    = Column(Integer, ForeignKey("pages.id"), nullable=False)
    lang       = Column(String(5), nullable=False)
    question   = Column(String, nullable=False)
    answer     = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0)

    page = relationship("Page", back_populates="faqs")


# ─────────────────────────────────────────────────────────────────────
# KATEGORİ CMS — Kategori sayfaları için içerik, SEO ve FAQ
# ─────────────────────────────────────────────────────────────────────

class CategoryContent(Base):
    """
    Her ürün kategorisi için CMS içeriği.
    category_key: CATEGORY_LABELS'daki Türkçe anahtar (ör. "Genel Temizlik")
    category_slug: URL'de kullanılan slug (ör. "genel-temizlik")
    """
    __tablename__ = "category_contents"

    id            = Column(Integer, primary_key=True, index=True)
    category_key  = Column(String, unique=True, index=True, nullable=False)
    category_slug = Column(String, unique=True, index=True, nullable=False)
    is_published  = Column(Integer, default=1)
    sort_order    = Column(Integer, default=0)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    translations = relationship(
        "CategoryTranslation",
        back_populates="category",
        cascade="all, delete-orphan",
    )
    faqs = relationship(
        "CategoryFaq",
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="CategoryFaq.sort_order",
    )

    def get_translation(self, lang: str) -> "CategoryTranslation":
        for t in self.translations:
            if t.lang == lang:
                return t
        for t in self.translations:
            if t.lang == "en":
                return t
        return self.translations[0] if self.translations else None


class CategoryTranslation(Base):
    """Her kategori × dil için içerik ve SEO."""
    __tablename__ = "category_translations"
    __table_args__ = (
        UniqueConstraint("category_id", "lang", name="uq_cat_lang"),
    )

    id               = Column(Integer, primary_key=True, index=True)
    category_id      = Column(Integer, ForeignKey("category_contents.id"), nullable=False)
    lang             = Column(String(5), nullable=False)
    title            = Column(String, nullable=True)
    intro            = Column(Text, nullable=True)   # Kısa giriş metni (hero altı)
    body             = Column(Text, nullable=True)   # Uzun HTML içerik (ürün listesi altı)
    meta_title       = Column(String, nullable=True)
    meta_description = Column(String, nullable=True)
    og_title         = Column(String, nullable=True)
    og_description   = Column(String, nullable=True)

    category = relationship("CategoryContent", back_populates="translations")


class CategoryFaq(Base):
    """Kategori başına, dil başına SSS sorusu."""
    __tablename__ = "category_faqs"
    __table_args__ = (
        UniqueConstraint("category_id", "lang", "sort_order", name="uq_catfaq_lang_order"),
    )

    id          = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("category_contents.id"), nullable=False)
    lang        = Column(String(5), nullable=False)
    question    = Column(String, nullable=False)
    answer      = Column(Text, nullable=False)
    sort_order  = Column(Integer, default=0)

    category = relationship("CategoryContent", back_populates="faqs")


# ─────────────────────────────────────────────────────────────────────
# ANASAYFA CMS — Her dil için anasayfa içeriği (JSON blob)
# ─────────────────────────────────────────────────────────────────────

class HomepageContent(Base):
    """
    Dil başına anasayfa içerik deposu.
    data: Tüm bölümlerin JSON olarak tutulduğu tek alan.
    """
    __tablename__ = "homepage_contents"

    id         = Column(Integer, primary_key=True, index=True)
    lang       = Column(String(5), unique=True, nullable=False, index=True)
    data       = Column(Text, nullable=True)       # JSON blob
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_data(self) -> dict:
        import json
        if self.data:
            try:
                return json.loads(self.data)
            except Exception:
                return {}
        return {}

    def set_data(self, d: dict):
        import json
        from sqlalchemy.orm.attributes import flag_modified
        self.data = json.dumps(d, ensure_ascii=False)
        flag_modified(self, "data")   # SQLAlchemy'ye Text alanının değiştiğini bildir


class SiteSettings(Base):
    """
    Tek satır site ayarları (singleton tablo).
    id her zaman 1'dir.
    """
    __tablename__ = "site_settings"

    id                 = Column(Integer, primary_key=True, default=1)
    site_name          = Column(String, default="Heni")
    logo_url           = Column(String, nullable=True)
    logo_white_url     = Column(String, nullable=True)   # Koyu header (scroll) için beyaz logo
    favicon_url        = Column(String, nullable=True)
    contact_email      = Column(String, nullable=True)
    contact_phone      = Column(String, nullable=True)
    contact_address    = Column(String, nullable=True)
    social_linkedin    = Column(String, nullable=True)
    social_instagram   = Column(String, nullable=True)
    social_twitter     = Column(String, nullable=True)
    social_whatsapp    = Column(String, nullable=True)
    seo_title_template = Column(String, nullable=True)
    seo_description    = Column(String, nullable=True)
    analytics_code     = Column(Text, nullable=True)
    custom_css         = Column(Text, nullable=True)
    # Footer (anasayfa alt bilgi alanı)
    footer_description   = Column(Text, nullable=True)
    footer_copyright_lead = Column(String, nullable=True)  # Ana telif metni: "© 2024 Heni. All rights reserved."
    footer_copyright     = Column(String, nullable=True)   # Son ek: "| Industrial Manufacturing Excellence"
    footer_columns       = Column(Text, nullable=True)    # JSON: [{"title":"Company","links":[{"label":"About Us","url":"#about"},...]}, ...]
    footer_bg_image_url  = Column(String, nullable=True)
    i18n                 = Column(Text, nullable=True)   # JSON: {"en":{...},"tr":{...},...} — dil bazlı metinler
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_footer_columns(self):
        """Footer sütunlarını JSON'dan listeye çevirir (legacy tek dil)."""
        import json
        if self.footer_columns:
            try:
                return json.loads(self.footer_columns)
            except Exception:
                pass
        return []

    def get_i18n_data(self):
        """i18n JSON'unu dict olarak döner."""
        import json
        if self.i18n:
            try:
                return json.loads(self.i18n)
            except Exception:
                pass
        return {}
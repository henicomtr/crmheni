from .models import User, CategoryContent, HomepageContent, ProductRating, ServicePageContent
from .auth import hash_password
from .database import SessionLocal

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .database import Base, engine
from .routes_admin import router as admin_router
from .routes_showroom import router as showroom_router
from .routes_webhook import router as webhook_router
from .routes_pricing import router as pricing_router
from .routes_feeds import router as feeds_router
from sqlalchemy import text, inspect
import os

# NOT: LangMiddleware şu an devre dışı.
# Tüm dil rotaları manuel çalışır:
#   /         → EN (varsayılan, ana sayfa)
#   /tr       → TR
#   /de       → DE
#   /fr       → FR
#   /product/{slug}      → EN
#   /tr/urun/{slug}      → TR
#   /de/produkt/{slug}   → DE
#   /fr/produit/{slug}   → FR
# Hazır olunca lang.py'daki LangMiddleware'i
# tekrar ekleyebilirsiniz.

# Tabloları oluştur (PostgreSQL'de Alembic yönetir, bu satır lokal/ilk kurulum için kalır)
Base.metadata.create_all(bind=engine)

# ── SiteSettings tablo migrasyonu ──────────────────────────────────
def _migrate_site_settings():
    """
    Eski SQLite kurulumları için eksik sütunları ekler.
    PostgreSQL'de bu kolonlar Alembic migration'ında zaten mevcut,
    fonksiyon hata vermeden atlar.
    """
    _new_cols = [
        ("social_whatsapp",       "VARCHAR"),
        ("seo_title_template",    "VARCHAR"),
        ("seo_description",       "VARCHAR"),
        ("analytics_code",        "TEXT"),
        ("custom_css",            "TEXT"),
        ("footer_description",    "TEXT"),
        ("footer_copyright_lead", "VARCHAR"),
        ("footer_copyright",      "VARCHAR"),
        ("footer_columns",        "TEXT"),
        ("footer_bg_image_url",   "VARCHAR"),
        ("i18n",                  "TEXT"),
        ("logo_white_url",        "VARCHAR"),
        ("default_og_image",      "VARCHAR"),
        ("cert_logo_iso9001_url",  "VARCHAR"),
        ("cert_logo_iso14001_url", "VARCHAR"),
        ("cert_logo_iso45001_url", "VARCHAR"),
        ("cert_logo_gmp_url",      "VARCHAR"),
        ("cert_logo_ce_url",       "VARCHAR"),
        ("cert_logo_fda_url",      "VARCHAR"),
        ("cert_logo_vegan_url",    "VARCHAR"),
        ("showroom_i18n_meta",     "TEXT"),
    ]
    insp = inspect(engine)
    if "site_settings" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("site_settings")}
    with engine.connect() as conn:
        for col_name, col_type in _new_cols:
            if col_name not in existing:
                # Sadece SQLite'ta çalışır; PostgreSQL'de kolon zaten var
                try:
                    conn.execute(text(f"ALTER TABLE site_settings ADD COLUMN {col_name} {col_type}"))
                except Exception:
                    pass  # PostgreSQL'de kolon zaten varsa hatayı yut
        conn.commit()

_migrate_site_settings()

# ── QuoteRequest tablo migrasyonu ───────────────────────────────────
def _migrate_quote_requests():
    """
    Eski SQLite kurulumları için currency sütununu ekler.
    PostgreSQL'de Alembic migration'ında zaten mevcut.
    """
    insp = inspect(engine)
    if "quote_requests" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("quote_requests")}
    with engine.connect() as conn:
        if "currency" not in existing:
            try:
                conn.execute(text("ALTER TABLE quote_requests ADD COLUMN currency VARCHAR DEFAULT 'USD'"))
            except Exception:
                pass  # PostgreSQL'de kolon zaten varsa hatayı yut
        conn.commit()

_migrate_quote_requests()

# ── QuoteRequest v2 migrasyonu: is_read, last_contacted_at ──────────
def _migrate_quote_requests_v2():
    """is_read ve last_contacted_at kolonlarını ekler."""
    insp = inspect(engine)
    if "quote_requests" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("quote_requests")}

    # Her kolon için bağımsız connection: bir hata diğerini etkilemez
    if "is_read" not in existing:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE quote_requests ADD COLUMN is_read BOOLEAN DEFAULT 0"))
                conn.commit()
        except Exception:
            pass

    if "last_contacted_at" not in existing:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE quote_requests ADD COLUMN last_contacted_at TIMESTAMP"))
                conn.commit()
        except Exception:
            pass

_migrate_quote_requests_v2()


# ── RequestMessage tablosu — create_all kapsamında ama güvence için explicit ──
def _migrate_request_messages():
    """request_messages tablosunu oluşturur (yoksa)."""
    from .models import RequestMessage as _RM
    Base.metadata.create_all(bind=engine, tables=[_RM.__table__])

_migrate_request_messages()

# ── SiteSettings v2: SMTP + Evolution API kolonları ─────────────────
def _migrate_site_settings_v2():
    """SMTP ve Evolution API ayar kolonlarını ekler."""
    _new_cols = [
        ("smtp_host",          "VARCHAR"),
        ("smtp_port",          "INTEGER"),
        ("smtp_user",          "VARCHAR"),
        ("smtp_password",      "VARCHAR"),
        ("smtp_from_email",    "VARCHAR"),
        ("evolution_api_url",  "VARCHAR"),
        ("evolution_api_key",  "VARCHAR"),
        ("evolution_instance", "VARCHAR"),
    ]
    insp = inspect(engine)
    if "site_settings" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("site_settings")}
    # Her kolon için bağımsız connection: bir hata diğerini etkilemez
    for col_name, col_type in _new_cols:
        if col_name not in existing:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE site_settings ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
            except Exception:
                pass

_migrate_site_settings_v2()

# ── SiteSettings v3: IMAP kolonları ─────────────────────────────────
def _migrate_site_settings_v3():
    """IMAP gelen kutusu ayar kolonlarını ekler."""
    _new_cols = [
        ("imap_host",     "VARCHAR"),
        ("imap_port",     "INTEGER"),
        ("imap_user",     "VARCHAR"),
        ("imap_password", "VARCHAR"),
    ]
    insp = inspect(engine)
    if "site_settings" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("site_settings")}
    for col_name, col_type in _new_cols:
        if col_name not in existing:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE site_settings ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
            except Exception:
                pass

_migrate_site_settings_v3()

# ── SiteSettings v4: CRM kendi URL'si (webhook kaydı için) ──────────
def _migrate_site_settings_v4():
    """crm_base_url kolonunu ekler — Evolution API webhook kaydında kullanılır."""
    insp = inspect(engine)
    if "site_settings" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("site_settings")}
    if "crm_base_url" not in existing:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE site_settings ADD COLUMN crm_base_url VARCHAR"))
                conn.commit()
        except Exception:
            pass

_migrate_site_settings_v4()

# ── RequestMessage: direction kolonu ────────────────────────────────
def _migrate_request_messages_v2():
    """direction (outgoing/incoming) kolonunu ekler."""
    insp = inspect(engine)
    if "request_messages" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("request_messages")}
    if "direction" not in existing:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE request_messages ADD COLUMN direction VARCHAR(20) DEFAULT 'outgoing'"))
                conn.commit()
        except Exception:
            pass

_migrate_request_messages_v2()

# ── Products tablo migrasyonu ────────────────────────────────────────
def _migrate_products():
    """
    Eski SQLite kurulumları için products tablosuna rating_count sütunu ekler.
    PostgreSQL'de Alembic migration'ında zaten mevcut.
    """
    insp = inspect(engine)
    if "products" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("products")}
    if "rating_count" not in existing:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE products ADD COLUMN rating_count INTEGER DEFAULT 0"))
                conn.commit()
        except Exception:
            pass
    if "updated_at" not in existing:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE products ADD COLUMN updated_at TIMESTAMP"))
                conn.commit()
        except Exception:
            pass

_migrate_products()

# ── CategoryContent seed ────────────────────────────────────────────
def _seed_categories():
    """Tüm kategoriler için CategoryContent kaydı oluşturur (yoksa)."""
    from .routes_showroom import CATEGORY_SLUGS
    _db = SessionLocal()
    try:
        for cat_key, cat_slug in CATEGORY_SLUGS.items():
            exists = _db.query(CategoryContent).filter(CategoryContent.category_key == cat_key).first()
            if not exists:
                cc = CategoryContent(category_key=cat_key, category_slug=cat_slug)
                _db.add(cc)
        _db.commit()
    finally:
        _db.close()

_seed_categories()

# ── HomepageContent seed ────────────────────────────────────────────
def _seed_homepage():
    """Desteklenen her dil için boş HomepageContent kaydı oluşturur (yoksa)."""
    LANGS = ["en", "tr", "de", "fr", "ar", "ru", "es"]
    _db = SessionLocal()
    try:
        for lc in LANGS:
            exists = _db.query(HomepageContent).filter(HomepageContent.lang == lc).first()
            if not exists:
                _db.add(HomepageContent(lang=lc, data="{}"))
        _db.commit()
    finally:
        _db.close()

_seed_homepage()


# ── ServicePageContent tablosu + seed + JSON→DB migrasyonu ─────────
def _seed_service_pages():
    """
    service_page_contents tablosunu oluşturur (yoksa) ve
    deterjan/kozmetik/parfüm × 7 dil için kayıt açar.
    Eski data/pages/ JSON dosyaları varsa içeriklerini tek seferlik
    DB'ye taşır — dolu kayıtlara dokunmaz.
    """
    import json as _jsp
    import os as _os
    from .models import ServicePageContent as _SPC

    # Tabloyu oluştur (PostgreSQL'de yoksa CREATE TABLE çalışır, varsa atlar)
    Base.metadata.create_all(bind=engine, tables=[_SPC.__table__])

    LANGS = ["en", "tr", "de", "fr", "ar", "ru", "es"]
    SLUGS = ["deterjan", "kozmetik", "parfum"]

    _db = SessionLocal()
    try:
        for slug in SLUGS:
            for lc in LANGS:
                exists = _db.query(ServicePageContent).filter(
                    ServicePageContent.slug == slug,
                    ServicePageContent.lang == lc,
                ).first()
                if exists:
                    continue  # Kayıt var — dokunma

                # Eski JSON dosyası varsa içeriği taşı
                json_path = _os.path.join(
                    _os.path.dirname(__file__), "..", "data", "pages", slug, f"{lc}.json"
                )
                initial_data = "{}"
                if _os.path.isfile(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            parsed = _jsp.load(f)
                        if parsed:
                            initial_data = _jsp.dumps(parsed, ensure_ascii=False)
                    except Exception:
                        pass

                _db.add(ServicePageContent(slug=slug, lang=lc, data=initial_data))

        _db.commit()
    finally:
        _db.close()

_seed_service_pages()


# ── HomepageContent veri migrasyonu ─────────────────────────────────
def _migrate_homepage_null_data():
    """data=NULL olan homepage_contents kayıtlarını '{}' ile günceller.
    ar/ru/es gibi sonradan eklenen dillerin seed edilmiş ama boş kalan
    kayıtları showroom'da EN'e fallback yapar; bu migrasyon bunu düzeltir."""
    _db = SessionLocal()
    try:
        from sqlalchemy import text
        _db.execute(
            text("UPDATE homepage_contents SET data = '{}' WHERE data IS NULL")
        )
        _db.commit()
    except Exception:
        _db.rollback()
    finally:
        _db.close()

_migrate_homepage_null_data()

# ── Users tablo migrasyonu ──────────────────────────────────────────
def _migrate_users():
    """
    users tablosuna is_superadmin ve permissions kolonlarını ekler.
    Her ALTER TABLE ayrı transaction'da çalışır — PostgreSQL uyumlu.
    """
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("users")}

    # Her kolon için bağımsız transaction: biri başarısız olsa diğeri çalışır
    if "is_superadmin" not in existing:
        try:
            with engine.connect() as conn:
                # PostgreSQL'de BOOLEAN DEFAULT FALSE; SQLite'da da geçerli
                conn.execute(text("ALTER TABLE users ADD COLUMN is_superadmin BOOLEAN DEFAULT FALSE"))
                conn.commit()
        except Exception:
            pass  # Kolon zaten varsa hatayı yut

    if "permissions" not in existing:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT '[]'"))
                conn.commit()
        except Exception:
            pass  # Kolon zaten varsa hatayı yut

_migrate_users()


# ── pages / page_translations tablo migrasyonu ─────────────────────
def _migrate_pages():
    """
    pages tablosuna shared_content,
    page_translations tablosuna content kolonu ekler.
    Her ALTER TABLE ayrı transaction'da çalışır — PostgreSQL uyumlu.
    """
    insp = inspect(engine)
    tables = insp.get_table_names()

    if "pages" in tables:
        existing = {c["name"] for c in insp.get_columns("pages")}
        if "shared_content" not in existing:
            try:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE pages ADD COLUMN shared_content TEXT"))
                    conn.commit()
            except Exception:
                pass  # Kolon zaten varsa hatayı yut

    if "page_translations" in tables:
        existing = {c["name"] for c in insp.get_columns("page_translations")}
        if "content" not in existing:
            try:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE page_translations ADD COLUMN content TEXT"))
                    conn.commit()
            except Exception:
                pass  # Kolon zaten varsa hatayı yut


_migrate_pages()

# ── Stok tabloları migrasyonu ───────────────────────────────────────
def _migrate_stock():
    """
    stock_items ve stock_consumptions tablolarını oluşturur (yoksa).
    Base.metadata.create_all zaten yeni tabloları ekler; bu fonksiyon
    SQLite'da eski kurulumlar için güvencedir.
    """
    from .models import StockItem, StockConsumption  # noqa: F401 — modeli register et
    Base.metadata.create_all(bind=engine, tables=[
        StockItem.__table__,
        StockConsumption.__table__,
    ])

_migrate_stock()

# ── Admin kullanıcı seed ────────────────────────────────────────────
def _seed_admin():
    """Varsayılan admin kullanıcısını oluşturur (yoksa) veya superadmin olarak işaretler."""
    admin_email    = os.getenv("ADMIN_EMAIL", "henicomtr@gmail.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "123456")
    _db = SessionLocal()
    try:
        admin = _db.query(User).filter(User.email == admin_email).first()
        if not admin:
            new_admin = User(
                email=admin_email,
                password=hash_password(admin_password),
                role="admin",
                is_superadmin=True,
                permissions="[]"
            )
            _db.add(new_admin)
            _db.commit()
        elif not admin.is_superadmin:
            # Mevcut admin varsa superadmin yap
            admin.is_superadmin = True
            _db.commit()
    finally:
        _db.close()

_seed_admin()

from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

app = FastAPI(title="HENİ CRM")

# Session middleware — secret key env'den okunur
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "fallback-sadece-development-icin")
)


class HttpsRedirectMiddleware(BaseHTTPMiddleware):
    """
    HTTP → HTTPS yönlendirme middleware'i.
    Nginx gibi bir reverse proxy arkasında çalışırken X-Forwarded-Proto
    header'ını kontrol eder. Direkt HTTP geliyorsa HTTPS'e yönlendirir.
    Robots.txt ve sitemap gibi crawler endpoint'lerini de kapsar.
    """
    async def dispatch(self, request, call_next):
        # Forwarded-Proto header'ı nginx tarafından set edilir
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        # Direkt HTTP bağlantısı ve proxy'den geçmemiş ise yönlendir
        if forwarded_proto == "http":
            https_url = str(request.url).replace("http://", "https://", 1)
            return RedirectResponse(url=https_url, status_code=301)
        return await call_next(request)


app.add_middleware(HttpsRedirectMiddleware)


# Statik dosya uzantılarına göre cache süresi
# NOT: CSS immutable olmamalı — deploy sonrası değişebilir, URL'de ?v= ile bust edilir
_CACHE_1_YEAR  = "public, max-age=31536000, immutable"   # görsel, font (değişmez varlıklar)
_CACHE_1_WEEK  = "public, max-age=604800"                # js dosyaları
_CACHE_1_HOUR  = "public, max-age=3600, must-revalidate" # css — her deploy'da ?v= ile güncellenir
_IMMUTABLE_EXTS = {".webp", ".jpg", ".jpeg", ".png", ".gif", ".svg",
                   ".woff", ".woff2", ".ttf", ".otf", ".ico"}
_WEEK_EXTS      = {".js"}
_HOUR_EXTS      = {".css"}


class StaticCacheMiddleware(BaseHTTPMiddleware):
    """
    /static/ altındaki dosyalara uzantıya göre Cache-Control header ekler.
    Nginx reverse proxy arkasında çalışırken bile etkilidir.
    """
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/"):
            # Uzantıyı al (query string olmadan)
            ext = os.path.splitext(path.split("?")[0])[1].lower()
            if ext in _IMMUTABLE_EXTS:
                response.headers["Cache-Control"] = _CACHE_1_YEAR
            elif ext in _WEEK_EXTS:
                response.headers["Cache-Control"] = _CACHE_1_WEEK
            elif ext in _HOUR_EXTS:
                response.headers["Cache-Control"] = _CACHE_1_HOUR
        return response


app.add_middleware(StaticCacheMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(admin_router)
app.include_router(feeds_router)     # catch-all /{slug}'den önce kayıtlı olmalı
app.include_router(webhook_router)   # showroom catch-all'dan önce kayıtlı olmalı
app.include_router(showroom_router)
app.include_router(pricing_router)


@app.on_event("startup")
async def on_startup():
    """Uygulama ayağa kalktığında IMAP polling ve Evolution webhook kaydını başlatır."""
    from .routes_webhook import start_imap_polling, _register_evolution_webhook
    start_imap_polling(app)
    await _register_evolution_webhook()
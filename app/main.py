from .models import User, CategoryContent, HomepageContent, ProductRating
from .auth import hash_password
from .database import SessionLocal

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .database import Base, engine
from .routes_admin import router as admin_router
from .routes_showroom import router as showroom_router
from .routes_webhook import router as webhook_router
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
    with engine.connect() as conn:
        if "rating_count" not in existing:
            try:
                conn.execute(text("ALTER TABLE products ADD COLUMN rating_count INTEGER DEFAULT 0"))
            except Exception:
                pass
        # Eski kurulumlar için updated_at kolonu ekle (TIMESTAMP: PostgreSQL uyumlu)
        if "updated_at" not in existing:
            try:
                conn.execute(text("ALTER TABLE products ADD COLUMN updated_at TIMESTAMP"))
            except Exception:
                pass
        conn.commit()

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
                _db.add(HomepageContent(lang=lc))
        _db.commit()
    finally:
        _db.close()

_seed_homepage()

# ── Admin kullanıcı seed ────────────────────────────────────────────
def _seed_admin():
    """Varsayılan admin kullanıcısını oluşturur (yoksa)."""
    admin_email    = os.getenv("ADMIN_EMAIL", "henicomtr@gmail.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "123456")
    _db = SessionLocal()
    try:
        admin = _db.query(User).filter(User.email == admin_email).first()
        if not admin:
            new_admin = User(
                email=admin_email,
                password=hash_password(admin_password),
                role="admin"
            )
            _db.add(new_admin)
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

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(admin_router)
app.include_router(showroom_router)
app.include_router(webhook_router)
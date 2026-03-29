# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request, Form, Depends, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone, timedelta as _timedelta
from jose import jwt, JWTError
from typing import Optional
import shutil
import os
import hmac
import hashlib

from .database import get_db
from .auth import verify_password, create_token
from .currency_service import get_rates, FALLBACK_RATES, format_price, LANG_CURRENCY
from .models import (
    User, Product, ProductTranslation, Customer, Supplier,
    Lead, Order, FinanceTransaction, QuoteRequest, AccountTransaction,
    Page, PageTranslation, FaqItem, SiteSettings,
    CategoryContent, CategoryTranslation, CategoryFaq,
    HomepageContent,
)
from .config import SECRET_KEY, ALGORITHM, CATEGORIES

SUPPORTED_LANGS = ["en", "tr", "de", "fr", "ar", "ru", "es"]

LANG_LABELS = {
    "en": "🇬🇧 English", "tr": "🇹🇷 Türkçe", "de": "🇩🇪 Deutsch",
    "fr": "🇫🇷 Français", "ar": "🇸🇦 العربية", "ru": "🇷🇺 Русский", "es": "🇪🇸 Español",
}

# Media dosyaları: /static/css, /static/js, /static/upload/*
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
UPLOAD_DIR_IMAGES = os.path.join(STATIC_DIR, "upload", "images")
UPLOAD_DIR_VIDEOS = os.path.join(STATIC_DIR, "upload", "videos")
UPLOAD_DIR_DOCS = os.path.join(STATIC_DIR, "upload", "doc")

# TinyMCE görsel upload + logo/fav burada saklanır
UPLOAD_DIR = UPLOAD_DIR_IMAGES

for _d in (UPLOAD_DIR_IMAGES, UPLOAD_DIR_VIDEOS, UPLOAD_DIR_DOCS):
    os.makedirs(_d, exist_ok=True)

# Anasayfa görselleri — aynı media standardı (/static/upload/images)
IMAGES_DIR = UPLOAD_DIR_IMAGES
os.makedirs(IMAGES_DIR, exist_ok=True)

CATEGORY_LABELS = {
    "Cilt Bakım":          {"tr": "Cilt Bakım",          "en": "Skin Care",            "de": "Hautpflege",         "fr": "Soin de la peau"},
    "Saç Bakım":           {"tr": "Saç Bakım",           "en": "Hair Care",            "de": "Haarpflege",         "fr": "Soin des cheveux"},
    "Kişisel Bakım":       {"tr": "Kişisel Bakım",       "en": "Personal Care",        "de": "Körperpflege",       "fr": "Soins personnels"},
    "Makyaj":              {"tr": "Makyaj",              "en": "Makeup",               "de": "Make-up",            "fr": "Maquillage"},
    "Parfüm":              {"tr": "Parfüm",              "en": "Perfume",              "de": "Parfüm",             "fr": "Parfum"},
    "Ortam Kokuları":      {"tr": "Ortam Kokuları",      "en": "Room Fragrances",      "de": "Raumdüfte",          "fr": "Senteurs d'intérieur"},
    "Genel Temizlik":      {"tr": "Genel Temizlik",      "en": "General Cleaning",     "de": "Allgemeinreinigung", "fr": "Nettoyage général"},
    "Çamaşır Yıkama":     {"tr": "Çamaşır Yıkama",     "en": "Laundry",              "de": "Wäsche",             "fr": "Lessive"},
    "Bulaşık Yıkama":     {"tr": "Bulaşık Yıkama",     "en": "Dishwashing",          "de": "Geschirrspülen",     "fr": "Vaisselle"},
    "Temizlik Malzemeleri":{"tr": "Temizlik Malzemeleri","en": "Cleaning Supplies",    "de": "Reinigungsmittel",   "fr": "Produits ménagers"},
    "Ambalaj":             {"tr": "Ambalaj",             "en": "Packaging",            "de": "Verpackung",         "fr": "Emballage"},
    "Kozmetik Hammadde":   {"tr": "Kozmetik Hammadde",   "en": "Cosmetic Raw Material","de": "Kosmetik-Rohstoffe", "fr": "Matière première cosmétique"},
    "Temizlik Hammadde":   {"tr": "Temizlik Hammadde",   "en": "Cleaning Raw Material","de": "Reinigungs-Rohstoffe","fr": "Matière première ménagère"},
}

def _categories_ui():
    """Admin panel için TR kategori isimleri."""
    return {k: v.get("tr", k) for k, v in CATEGORY_LABELS.items()}


def _convert_to_usd(amount: float, currency: str) -> float:
    """
    Farklı para birimlerindeki tutarları USD'ye çevirir.
    amount: Orijinal tutar
    currency: Para birimi kodu (TRY, USD, EUR, GBP)
    Returns: USD cinsinden tutar
    """
    if currency == "USD":
        return amount
    
    rates = get_rates()
    
    if currency == "TRY":
        return amount / rates.get("USD_TRY", FALLBACK_RATES["USD_TRY"])
    elif currency == "EUR":
        return amount * rates.get("EUR_USD", FALLBACK_RATES["EUR_USD"])
    elif currency == "GBP":
        # GBP → USD için yaklaşık oran (1 GBP ≈ 1.27 USD)
        return amount * 1.27
    
    # Bilinmeyen para birimi için tutarı olduğu gibi döndür
    return amount


def _calculate_account_balance(db: Session, customer_id: int = None, supplier_id: int = None) -> dict:
    """
    Müşteri veya tedarikçi için cari hesap bakiyesini hesaplar.
    Her para birimi kendi içinde ayrı tutulur; USD toplamı da ek olarak hesaplanır.
    """
    query = db.query(AccountTransaction)

    if customer_id:
        query = query.filter(AccountTransaction.customer_id == customer_id)
    elif supplier_id:
        query = query.filter(AccountTransaction.supplier_id == supplier_id)
    else:
        return {
            "total_debit_usd": 0.0, "total_credit_usd": 0.0, "balance_usd": 0.0,
            "native": {}, "dominant_currency": "USD", "transactions": []
        }

    transactions = query.order_by(AccountTransaction.transaction_date.desc()).all()

    total_debit_usd  = 0.0
    total_credit_usd = 0.0
    # Para birimi bazlı native toplamlar: {"TRY": {"debit": x, "credit": y}, ...}
    native: dict = {}

    for tx in transactions:
        cur = (tx.currency or "USD").upper()
        if cur not in native:
            native[cur] = {"debit": 0.0, "credit": 0.0}
        if tx.type == "debit":
            native[cur]["debit"] += tx.amount
            total_debit_usd += _convert_to_usd(tx.amount, cur)
        else:
            native[cur]["credit"] += tx.amount
            total_credit_usd += _convert_to_usd(tx.amount, cur)

    # Bakiye hesabı (USD cinsinden)
    if customer_id:
        balance_usd = total_debit_usd - total_credit_usd
    else:
        balance_usd = total_credit_usd - total_debit_usd

    # Native bakiyeler (her para birimi kendi içinde)
    native_balances = {}
    for cur, vals in native.items():
        if customer_id:
            native_balances[cur] = vals["debit"] - vals["credit"]
        else:
            native_balances[cur] = vals["credit"] - vals["debit"]

    # Dominant para birimi: en yüksek hacimli
    if native:
        dominant_currency = max(
            native.keys(),
            key=lambda c: native[c]["debit"] + native[c]["credit"]
        )
    else:
        dominant_currency = "USD"

    return {
        "total_debit_usd":  total_debit_usd,
        "total_credit_usd": total_credit_usd,
        "balance_usd":      balance_usd,
        "native":           native,
        "native_balances":  native_balances,
        "dominant_currency": dominant_currency,
        "transactions":     transactions,
    }


router = APIRouter()
templates = Jinja2Templates(directory="templates")

def _tr_datetime(dt):
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tr_dt = dt.astimezone(timezone(_timedelta(hours=3)))
    return tr_dt.strftime("%d.%m.%Y %H:%M")

templates.env.filters["tr_datetime"] = _tr_datetime

# Dosya tiplerine göre farklı klasörler
# - Görseller: /static/upload/images
# - Videolar:  /static/upload/videos
# - Dokümanlar: /static/upload/doc

# Hangi form alanı hangi klasöre ve hangi URL prefix'ine gider
FILE_FIELD_MAP = {
    "image":        ("image",  UPLOAD_DIR_IMAGES, "/static/upload/images/"),
    "product_video":("video",  UPLOAD_DIR_VIDEOS, "/static/upload/videos/"),
    "loading_video":("video",  UPLOAD_DIR_VIDEOS, "/static/upload/videos/"),
    "msds":         ("doc",    UPLOAD_DIR_DOCS,   "/static/upload/doc/"),
    "tds":          ("doc",    UPLOAD_DIR_DOCS,   "/static/upload/doc/"),
    "analysis_doc": ("doc",    UPLOAD_DIR_DOCS,   "/static/upload/doc/"),
    "quality_doc":  ("doc",    UPLOAD_DIR_DOCS,   "/static/upload/doc/"),
}

def save_upload(uploaded_file, upload_dir: str, url_prefix: str) -> str:
    """Dosyayı doğru klasöre kaydeder, URL'ini döner."""
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, uploaded_file.filename)
    with open(dest, "wb") as buf:
        shutil.copyfileobj(uploaded_file.file, buf)
    return url_prefix + uploaded_file.filename


def _is_jpeg_jpg_png_upload(upload_file) -> bool:
    """
    Sadece optimize edeceğimiz JPG/JPEG/PNG dosyalarını tespit eder.
    (Diğer formatlarda optimizasyon yapılmaz.)
    """
    if not upload_file:
        return False
    filename = getattr(upload_file, "filename", "") or ""
    ext = os.path.splitext(filename)[1].lower()
    content_type = (getattr(upload_file, "content_type", "") or "").lower()
    return (
        ext in (".jpg", ".jpeg", ".png")
        or content_type in ("image/jpeg", "image/png", "image/jpg")
    )


def _is_logo_filename(filename: str) -> bool:
    """Dosya adında 'logo' geçiyorsa True döner (büyük/küçük harf duyarsız)."""
    name = os.path.splitext(os.path.basename(filename or ""))[0].lower()
    return "logo" in name


async def optimize_and_save_image(file: UploadFile, upload_folder: str, is_logo: bool = False) -> str:
    """
    JPG/JPEG/PNG görsellerini optimize ederek kaydeder.

    - Normal görseller: WebP formatına dönüştürülür (max 1200px, kalite 75)
    - Logo görselleri (is_logo=True veya dosya adında 'logo' geçiyorsa):
      Orijinal format korunur (PNG → PNG, JPG → JPG). Şeffaflık (alfa kanalı)
      bozulmadan saklanır. Bu sayede arka planı şeffaf logolar görsel kalitesini
      kaybetmez.
    - Pillow invalid görsellerde hata fırlatmak yerine ham veriyi kaydeder
    """
    os.makedirs(upload_folder, exist_ok=True)

    import uuid
    from io import BytesIO

    from PIL import Image

    original_filename = getattr(file, "filename", "") or ""
    original_ext = os.path.splitext(original_filename)[1].lower()
    fallback_ext = original_ext if original_ext in (".jpg", ".jpeg", ".png") else ".jpg"

    # Dosya adında "logo" geçiyorsa da optimizasyondan muaf tut
    if not is_logo and _is_logo_filename(original_filename):
        is_logo = True

    # UploadFile stream'i tek seferde oku.
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:  # 5MB
        raise ValueError("File too large")

    uid = uuid.uuid4().hex[:12]

    # Boş dosyada çakışmayı önlemek için raw boş dosya üret.
    if not contents:
        raw_filename = f"img_{uid}{fallback_ext}"
        raw_path = os.path.join(upload_folder, raw_filename)
        with open(raw_path, "wb") as buf:
            buf.write(b"")
        return raw_filename

    try:
        img = Image.open(BytesIO(contents))
        img.load()

        # Maksimum boyut 1200 (aspect ratio koruyarak)
        max_dim = 1200
        if img.width > max_dim or img.height > max_dim:
            resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
            img.thumbnail((max_dim, max_dim), resample=resample)

        if is_logo:
            # Logo: orijinal formatı ve şeffaflığı koru
            save_ext = original_ext if original_ext in (".png", ".jpg", ".jpeg") else ".png"
            save_format = "PNG" if save_ext == ".png" else "JPEG"
            out_filename = f"img_{uid}{save_ext}"
            out_path = os.path.join(upload_folder, out_filename)

            if save_format == "JPEG":
                # JPEG alfa kanalını desteklemez; varsa beyaz arka plana yapıştır
                if img.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(out_path, "JPEG", quality=90, optimize=True)
            else:
                # PNG: RGBA/P modlarını koru (şeffaflık bozulmasın)
                if img.mode == "P":
                    img = img.convert("RGBA")
                elif img.mode not in ("RGBA", "RGB", "LA", "L"):
                    img = img.convert("RGBA")
                img.save(out_path, "PNG", optimize=True)

            print(f"[upload] Saved logo image (no WebP conversion): {out_filename}")
            return out_filename
        else:
            # Normal görsel: WebP'e dönüştür
            webp_filename = f"img_{uid}.webp"
            webp_path = os.path.join(upload_folder, webp_filename)

            # RGBA / P mode -> RGB (WebP için RGB kaydetmek üzere)
            if img.mode in ("RGBA", "LA"):
                alpha = img.split()[-1]
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img.convert("RGB"), mask=alpha)
                img = bg
            elif img.mode == "P":
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            img.save(webp_path, "WEBP", quality=75, optimize=True)
            print(f"[upload] Saved optimized image: {webp_filename}")
            return webp_filename

    except Exception as e:
        # Pillow invalid/bozuk dosyalarda crash etmesin diye hamı kaydet.
        raw_filename = f"img_{uid}{fallback_ext}"
        raw_path = os.path.join(upload_folder, raw_filename)
        with open(raw_path, "wb") as buf:
            buf.write(contents)
        print(f"[upload] Image optimization failed, saved raw: {raw_filename} ({e})")
        return raw_filename

# =========================================================
# AUTH GUARD
# =========================================================

def admin_required(token: Optional[str] = Cookie(None)):
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# =========================================================
# PIN KAPI & BRUTE-FORCE KORUMASI
# =========================================================

# Giriş kapısı PIN kodu (4 haneli)
_GATE_PIN = "5016"
# Ban süresi (dakika)
_BAN_MINUTES = 30
# İzin verilen maksimum yanlış deneme
_MAX_ATTEMPTS = 3

# Bellek tabanlı ban kayıtları: {ip: {"count": int, "blocked_until": datetime|None}}
_pin_attempts: dict = {}
_login_attempts: dict = {}


def _get_client_ip(request: Request) -> str:
    """İstemci IP adresini tespit eder (proxy arkasında da çalışır)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_banned(store: dict, ip: str) -> bool:
    """IP'nin aktif bir banlı olup olmadığını kontrol eder."""
    entry = store.get(ip)
    if not entry:
        return False
    blocked_until = entry.get("blocked_until")
    if blocked_until and datetime.now(timezone.utc) < blocked_until:
        return True
    # Ban süresi dolmuşsa kaydı temizle
    if blocked_until and datetime.now(timezone.utc) >= blocked_until:
        store.pop(ip, None)
    return False


def _ban_remaining_seconds(store: dict, ip: str) -> int:
    """Banlı IP için kalan saniyeyi döner."""
    entry = store.get(ip)
    if not entry:
        return 0
    blocked_until = entry.get("blocked_until")
    if blocked_until and datetime.now(timezone.utc) < blocked_until:
        delta = blocked_until - datetime.now(timezone.utc)
        return int(delta.total_seconds())
    return 0


def _record_failure(store: dict, ip: str) -> int:
    """Başarısız denemeyi kaydeder; yeni deneme sayısını döner.
    Limit aşılırsa IP'yi banlar ve 0 döner (banlama gerçekleşti)."""
    entry = store.setdefault(ip, {"count": 0, "blocked_until": None})
    entry["count"] += 1
    if entry["count"] >= _MAX_ATTEMPTS:
        entry["blocked_until"] = datetime.now(timezone.utc) + _timedelta(minutes=_BAN_MINUTES)
        entry["count"] = 0  # Sayaçı sıfırla (ban sonrası yeni süreç için)
    return entry["count"]


def _reset_attempts(store: dict, ip: str):
    """Başarılı girişte deneme sayacını sıfırlar."""
    store.pop(ip, None)


def _make_gate_cookie(secret: str) -> str:
    """PIN doğrulandığında kullanıcıya verilecek imzalı cookie değeri üretir."""
    return hmac.new(secret.encode(), b"heni_gate_ok", hashlib.sha256).hexdigest()


def _verify_gate_cookie(secret: str, value: str) -> bool:
    """Cookie değerinin geçerliliğini HMAC ile doğrular."""
    expected = hmac.new(secret.encode(), b"heni_gate_ok", hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, value)


# =========================================================
# PIN KAPISI ROUTE'LARI
# =========================================================

@router.get("/esk", response_class=HTMLResponse)
def pin_gate_page(request: Request):
    """PIN giriş ekranını gösterir. Zaten giriş yapılmışsa panele yönlendirir."""
    ip = _get_client_ip(request)

    # Aktif JWT token varsa direk panele gönder
    token = request.cookies.get("token")
    if token:
        try:
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return RedirectResponse("/esk/dashboard", status_code=302)
        except JWTError:
            pass

    # IP banlı mı kontrol et
    if _is_banned(_pin_attempts, ip):
        kalan = _ban_remaining_seconds(_pin_attempts, ip)
        dakika = kalan // 60
        saniye = kalan % 60
        return templates.TemplateResponse("pin_gate.html", {
            "request": request,
            "banned": True,
            "ban_msg": f"Çok fazla hatalı deneme. {dakika} dk {saniye} sn sonra tekrar deneyin.",
        })

    return templates.TemplateResponse("pin_gate.html", {
        "request": request,
        "banned": False,
        "error": request.query_params.get("error"),
    })


@router.post("/esk/verify")
def pin_verify(
    request: Request,
    pin: str = Form(...),
):
    """PIN doğrulama — doğruysa login sayfasına, yanlışsa ban kontrolüyle geri döner."""
    ip = _get_client_ip(request)

    # IP banlı mı
    if _is_banned(_pin_attempts, ip):
        kalan = _ban_remaining_seconds(_pin_attempts, ip)
        dakika = kalan // 60
        saniye = kalan % 60
        return templates.TemplateResponse("pin_gate.html", {
            "request": request,
            "banned": True,
            "ban_msg": f"Çok fazla hatalı deneme. {dakika} dk {saniye} sn sonra tekrar deneyin.",
        })

    # PIN doğru mu
    if pin.strip() != _GATE_PIN:
        _record_failure(_pin_attempts, ip)
        if _is_banned(_pin_attempts, ip):
            kalan = _ban_remaining_seconds(_pin_attempts, ip)
            dakika = kalan // 60
            saniye = kalan % 60
            return templates.TemplateResponse("pin_gate.html", {
                "request": request,
                "banned": True,
                "ban_msg": f"Çok fazla hatalı deneme. {dakika} dk {saniye} sn sonra tekrar deneyin.",
            })
        return templates.TemplateResponse("pin_gate.html", {
            "request": request,
            "banned": False,
            "error": "Hatalı PIN. Lütfen tekrar deneyin.",
        })

    # PIN doğru — cookie set et ve login'e yönlendir
    _reset_attempts(_pin_attempts, ip)
    response = RedirectResponse("/esk/login", status_code=302)
    response.set_cookie(
        key="heni_gate",
        value=_make_gate_cookie(SECRET_KEY),
        httponly=True,
        samesite="lax",
        max_age=3600,  # 1 saat geçerli
    )
    return response


# =========================================================
# LOGIN
# =========================================================

@router.get("/esk/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Login sayfasını gösterir. PIN kapısı geçilmemişse /esk'e yönlendirir."""
    ip = _get_client_ip(request)

    # PIN cookie kontrolü
    gate_cookie = request.cookies.get("heni_gate", "")
    if not _verify_gate_cookie(SECRET_KEY, gate_cookie):
        return RedirectResponse("/esk", status_code=302)

    # Login ban kontrolü
    if _is_banned(_login_attempts, ip):
        kalan = _ban_remaining_seconds(_login_attempts, ip)
        dakika = kalan // 60
        saniye = kalan % 60
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": f"Çok fazla hatalı giriş. {dakika} dk {saniye} sn sonra tekrar deneyin.",
            "banned": True,
        })

    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/esk/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Kullanıcı girişi — brute-force korumalı."""
    ip = _get_client_ip(request)

    # PIN cookie kontrolü
    gate_cookie = request.cookies.get("heni_gate", "")
    if not _verify_gate_cookie(SECRET_KEY, gate_cookie):
        return RedirectResponse("/esk", status_code=302)

    # Login ban kontrolü
    if _is_banned(_login_attempts, ip):
        kalan = _ban_remaining_seconds(_login_attempts, ip)
        dakika = kalan // 60
        saniye = kalan % 60
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": f"Çok fazla hatalı giriş. {dakika} dk {saniye} sn sonra tekrar deneyin.",
            "banned": True,
        })

    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(password, user.password):
        _record_failure(_login_attempts, ip)
        if _is_banned(_login_attempts, ip):
            kalan = _ban_remaining_seconds(_login_attempts, ip)
            dakika = kalan // 60
            saniye = kalan % 60
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": f"Çok fazla hatalı giriş. {dakika} dk {saniye} sn sonra tekrar deneyin.",
                "banned": True,
            })
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "E-posta veya şifre hatalı."}
        )

    # Başarılı giriş — deneme sayacını sıfırla
    _reset_attempts(_login_attempts, ip)
    token = create_token({"sub": user.email})

    response = RedirectResponse(url="/esk/dashboard", status_code=302)
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        samesite="lax"
    )
    return response


@router.get("/esk/logout")
def logout():
    response = RedirectResponse("/esk/login", status_code=302)
    response.delete_cookie("token")
    return response


# =========================================================
# DASHBOARD
# =========================================================

@router.get("/esk/dashboard", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):

    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    total_products = db.query(Product).count()
    total_stock = db.query(func.sum(Product.stock)).scalar() or 0
    sold_products = db.query(func.sum(Order.quantity)).scalar() or 0

    total_customers = db.query(Customer).count()
    total_suppliers = db.query(Supplier).count()
    total_requests = db.query(QuoteRequest).count()
    
    # Haftalık ve yıllık müşteri sayıları
    from datetime import timedelta
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    weekly_customers = db.query(Customer).filter(Customer.created_at >= week_ago).count()
    yearly_customers = db.query(Customer).filter(Customer.created_at >= year_start).count()

    # Finans verileri - Tüm işlemleri USD'ye çevir
    all_transactions = db.query(FinanceTransaction).all()
    
    total_income_usd = 0.0
    total_expense_usd = 0.0
    
    for tx in all_transactions:
        amount_usd = _convert_to_usd(tx.amount, tx.currency or "TRY")
        if tx.type == "income":
            total_income_usd += amount_usd
        else:
            total_expense_usd += amount_usd

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "total_products": total_products,
            "total_stock": total_stock,
            "sold_products": sold_products,
            "total_customers": total_customers,
            "total_suppliers": total_suppliers,
            "total_requests": total_requests,
            "weekly_customers": weekly_customers,
            "yearly_customers": yearly_customers,
            "total_income": total_income_usd,
            "total_expense": total_expense_usd
        }
    )


# =========================================================
# PRODUCTS
# =========================================================

@router.get("/esk/products", response_class=HTMLResponse)
def products_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):

    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    products = db.query(Product).all()

    return templates.TemplateResponse(
        "admin_products.html",
        {
            "request":       request,
            "products":      products,
            "categories":    CATEGORIES,
            "categories_ui": _categories_ui(),
        }
    )


@router.post("/esk/products/create")
async def create_product(
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    import re, unicodedata

    def slugify(text: str) -> str:
        TR_MAP = str.maketrans("çğışöüÇĞİŞÖÜ", "cgisouCGISOU")
        text = text.translate(TR_MAP)
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^\w\s-]", "", text).strip().lower()
        return re.sub(r"[\s_-]+", "-", text)

    form   = await request.form()
    LANGS  = ["en", "tr", "de", "fr"]

    # Evrensel alanlar
    category         = form.get("category", "")
    unit_price       = float(form.get("unit_price") or 0)
    stock            = int(form.get("stock") or 0)
    barcode          = form.get("barcode", "")
    export_countries = form.get("export_countries", "")
    pieces_per_box   = int(form.get("pieces_per_box") or 1)
    boxes_per_pallet = int(form.get("boxes_per_pallet") or 1)
    pallets_20ft     = int(form.get("pallets_20ft") or 10)
    pallets_40ft     = int(form.get("pallets_40ft") or 20)

    # Resim + diğer medya dosyaları (create sırasında)
    image_path = None
    image = form.get("image")
    if image and hasattr(image, "filename") and image.filename:
        if _is_jpeg_jpg_png_upload(image):
            try:
                optimized_fname = await optimize_and_save_image(image, UPLOAD_DIR_IMAGES)
                image_path = f"/static/upload/images/{optimized_fname}"
            except ValueError as e:
                if "too large" in str(e).lower():
                    return RedirectResponse("/esk/products?error=image_too_large", status_code=302)
                return RedirectResponse("/esk/products", status_code=302)
        else:
            image_path = save_upload(image, UPLOAD_DIR_IMAGES, "/static/upload/images/")
    
    # Diğer medya alanları (video, belgeler)
    extra_files = {}
    for field_name, (_, udir, uprefix) in FILE_FIELD_MAP.items():
        if field_name == "image":
            continue
        f = form.get(field_name)
        if f and hasattr(f, "filename") and f.filename:
            extra_files[field_name] = save_upload(f, udir, uprefix)

    # EN adından master slug üret
    name_en    = form.get("name_en", "").strip() or "urun"
    slug_en    = form.get("slug_en", "").strip()
    base_slug  = slugify(slug_en) if slug_en else slugify(name_en)

    slug = base_slug
    counter = 1
    while db.query(Product).filter(Product.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    new_product = Product(
        slug=slug,
        category=category,
        unit_price=unit_price,
        stock=stock,
        barcode=barcode,
        export_countries=export_countries,
        pieces_per_box=pieces_per_box,
        boxes_per_pallet=boxes_per_pallet,
        pallets_20ft=pallets_20ft,
        pallets_40ft=pallets_40ft,
        image=image_path,
        product_video=extra_files.get("product_video"),
        loading_video=extra_files.get("loading_video"),
        msds=extra_files.get("msds"),
        tds=extra_files.get("tds"),
        analysis_doc=extra_files.get("analysis_doc"),
        quality_doc=extra_files.get("quality_doc"),
    )

    db.add(new_product)
    db.flush()

    for lc in LANGS:
        lname = form.get(f"name_{lc}", "").strip()
        if not lname:
            continue  # boş dil sekmelerini atla
        lslug_raw = form.get(f"slug_{lc}", "").strip()
        lslug     = slugify(lslug_raw) if lslug_raw else slugify(lname)
        # EN slug zaten ayarlandı, diğerleri için çakışma kontrolü
        if lc != "en":
            base_ls = lslug
            c2 = 1
            while db.query(ProductTranslation).filter(ProductTranslation.slug == lslug).first():
                lslug = f"{base_ls}-{c2}"
                c2 += 1

        translation = ProductTranslation(
            product_id=new_product.id,
            lang=lc,
            name=lname,
            slug=lslug if lc != "en" else slug,
            short_description=form.get(f"short_description_{lc}", ""),
            long_description=form.get(f"long_description_{lc}", ""),
            meta_title=form.get(f"meta_title_{lc}", ""),
            meta_description=form.get(f"meta_description_{lc}", ""),
        )
        db.add(translation)

    db.commit()
    return RedirectResponse("/esk/products", status_code=302)



@router.get("/esk/products/delete/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):

    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()

    return RedirectResponse("/esk/products", status_code=302)


# =========================================================
# REQUESTS
# =========================================================

# =========================================================
# PRODUCT EDIT — GET
# =========================================================

@router.get("/esk/products/edit/{product_id}", response_class=HTMLResponse)
def edit_product_page(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse("/esk/products", status_code=302)

    categories_ui = _categories_ui()
    return templates.TemplateResponse(
        "admin_product_edit.html",
        {"request": request, "product": product, "categories_ui": categories_ui}
    )


# =========================================================
# PRODUCT UPDATE — POST
# =========================================================

@router.post("/esk/products/update/{product_id}")
async def update_product(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    import re, unicodedata

    def slugify(text: str) -> str:
        TR_MAP = str.maketrans("çğışöüÇĞİŞÖÜ", "cgisouCGISOU")
        text = text.translate(TR_MAP)
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^\w\s-]", "", text).strip().lower()
        return re.sub(r"[\s_-]+", "-", text)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse("/esk/products", status_code=302)

    form = await request.form()
    LANGS = ["en", "tr", "de", "fr", "ar", "ru", "es"]

    # Evrensel alanlar
    product.category         = form.get("category", product.category or "")
    product.unit_price       = float(form.get("unit_price") or product.unit_price)
    product.stock            = int(form.get("stock") or product.stock or 0)
    product.barcode          = form.get("barcode", product.barcode or "")
    product.export_countries = form.get("export_countries", product.export_countries or "")
    product.pieces_per_box   = int(form.get("pieces_per_box") or product.pieces_per_box or 1)
    product.boxes_per_pallet = int(form.get("boxes_per_pallet") or product.boxes_per_pallet or 1)
    product.pallets_20ft     = int(form.get("pallets_20ft") or product.pallets_20ft or 10)
    product.pallets_40ft     = int(form.get("pallets_40ft") or product.pallets_40ft or 20)

    # Master slug güncelle (formdan slug alanı varsa)
    new_master_slug = form.get("slug", "").strip()
    if new_master_slug:
        new_master_slug = slugify(new_master_slug)
        # Başka ürünle çakışıyor mu?
        conflict = db.query(Product).filter(
            Product.slug == new_master_slug,
            Product.id != product_id
        ).first()
        if not conflict:
            product.slug = new_master_slug

    # Resim & medya dosyaları — her biri kendi klasörüne
    for field_name, (_, udir, uprefix) in FILE_FIELD_MAP.items():
        uploaded = form.get(field_name)
        if uploaded and hasattr(uploaded, "filename") and uploaded.filename:
            if field_name == "image" and _is_jpeg_jpg_png_upload(uploaded):
                try:
                    optimized_fname = await optimize_and_save_image(uploaded, udir)
                    setattr(product, field_name, uprefix + optimized_fname)
                except ValueError as e:
                    if "too large" in str(e).lower():
                        return RedirectResponse(
                            f"/esk/products/edit/{product_id}?error=image_too_large",
                            status_code=302,
                        )
                    # Diğer durumlarda olduğu gibi kaydetmeyi bozmayalım.
                    url = save_upload(uploaded, udir, uprefix)
                    setattr(product, field_name, url)
            else:
                url = save_upload(uploaded, udir, uprefix)
                setattr(product, field_name, url)

    # Çeviriler — mevcut olanı güncelle, yoksa yeni oluştur
    for lc in LANGS:
        lname = form.get(f"name_{lc}", "").strip()
        if not lname:
            continue  # boş sekmeleri atla

        existing_t = next(
            (t for t in product.translations if t.lang == lc), None
        )

        lslug_raw = form.get(f"slug_{lc}", "").strip()
        lslug = slugify(lslug_raw) if lslug_raw else slugify(lname)

        # Slug çakışma kontrolü (kendisi hariç)
        conflict_t = db.query(ProductTranslation).filter(
            ProductTranslation.slug == lslug,
            ProductTranslation.product_id != product_id
        ).first()
        if conflict_t:
            base = lslug
            c = 1
            while db.query(ProductTranslation).filter(
                ProductTranslation.slug == lslug,
                ProductTranslation.product_id != product_id
            ).first():
                lslug = f"{base}-{c}"
                c += 1

        if existing_t:
            existing_t.name              = lname
            existing_t.slug              = lslug
            existing_t.short_description = form.get(f"short_description_{lc}", existing_t.short_description or "")
            existing_t.long_description  = form.get(f"long_description_{lc}", existing_t.long_description or "")
            existing_t.meta_title        = form.get(f"meta_title_{lc}", existing_t.meta_title or "")
            existing_t.meta_description  = form.get(f"meta_description_{lc}", existing_t.meta_description or "")
        else:
            new_t = ProductTranslation(
                product_id=product_id,
                lang=lc,
                name=lname,
                slug=lslug,
                short_description=form.get(f"short_description_{lc}", ""),
                long_description=form.get(f"long_description_{lc}", ""),
                meta_title=form.get(f"meta_title_{lc}", ""),
                meta_description=form.get(f"meta_description_{lc}", ""),
            )
            db.add(new_t)

    db.commit()
    return RedirectResponse(f"/esk/products/edit/{product_id}", status_code=302)


# =========================================================
# CUSTOMERS
# =========================================================

@router.get("/esk/customers", response_class=HTMLResponse)
def customers_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    from datetime import timedelta
    customers = db.query(Customer).order_by(Customer.created_at.desc()).all()
    week_ago  = datetime.utcnow() - timedelta(days=7)
    weekly_new   = sum(1 for c in customers if c.created_at and c.created_at >= week_ago)
    country_count = len(set(c.country for c in customers if c.country))

    # Her müşteri için cari bakiye hesapla
    customer_balances = {}
    for customer in customers:
        balance_data = _calculate_account_balance(db, customer_id=customer.id)
        dom = balance_data["dominant_currency"]
        nb  = balance_data["native_balances"]
        customer_balances[customer.id] = {
            "balance_usd":        balance_data["balance_usd"],
            "dominant_currency":  dom,
            "native_balance":     nb.get(dom, 0),
        }

    return templates.TemplateResponse("admin_customers.html", {
        "request": request,
        "customers": customers,
        "weekly_new": weekly_new,
        "country_count": country_count,
        "customer_balances": customer_balances,
    })


@router.post("/esk/customers/create")
def create_customer(
    request: Request,
    name: str = Form(...),
    country: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    contact_person: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    db.add(Customer(
        name=name, country=country or None, email=email or None,
        phone=phone or None, contact_person=contact_person or None,
        notes=notes or None
    ))
    db.commit()
    return RedirectResponse("/esk/customers", status_code=302)


@router.get("/esk/customers/edit/{customer_id}", response_class=HTMLResponse)
def edit_customer_page(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        return RedirectResponse("/esk/customers", status_code=302)

    # Cari hesap bakiyesi hesapla
    account_data = _calculate_account_balance(db, customer_id=customer_id)

    rates = get_rates()
    dom  = account_data["dominant_currency"]
    nb   = account_data["native_balances"]
    native = account_data["native"]

    return templates.TemplateResponse("admin_customer_edit.html", {
        "request":              request,
        "customer":             customer,
        "account_balance":      account_data["balance_usd"],
        "account_transactions": account_data["transactions"],
        "total_debit":          account_data["total_debit_usd"],
        "total_credit":         account_data["total_credit_usd"],
        "dominant_currency":    dom,
        "native_balances":      nb,
        "native_totals":        native,
        "rates":                rates,
    })


@router.post("/esk/customers/update/{customer_id}")
def update_customer(
    customer_id: int,
    name: str = Form(...),
    country: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    contact_person: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer:
        customer.name           = name
        customer.country        = country or None
        customer.email          = email or None
        customer.phone          = phone or None
        customer.contact_person = contact_person or None
        customer.notes          = notes or None
        db.commit()
    return RedirectResponse(f"/esk/customers/edit/{customer_id}", status_code=302)


@router.post("/esk/customers/delete/{customer_id}")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer:
        db.delete(customer)
        db.commit()
    return RedirectResponse("/esk/customers", status_code=302)


@router.post("/esk/customers/{customer_id}/account/add")
def add_customer_account_transaction(
    customer_id: int,
    type: str = Form(...),
    amount: float = Form(...),
    currency: str = Form("USD"),
    description: str = Form(""),
    reference_no: str = Form(""),
    transaction_date: str = Form(""),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    # Tarih parse
    tx_date = datetime.utcnow()
    if transaction_date:
        try:
            tx_date = datetime.strptime(transaction_date, "%Y-%m-%dT%H:%M") - _timedelta(hours=3)
        except ValueError:
            pass

    tx = AccountTransaction(
        type=type,
        amount=amount,
        currency=currency,
        description=description or None,
        reference_no=reference_no or None,
        customer_id=customer_id,
        transaction_date=tx_date,
    )
    db.add(tx)
    db.commit()
    
    return RedirectResponse(f"/esk/customers/edit/{customer_id}", status_code=302)


@router.post("/esk/customers/account/delete/{tx_id}")
def delete_customer_account_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    tx = db.query(AccountTransaction).filter(AccountTransaction.id == tx_id).first()
    if tx and tx.customer_id:
        customer_id = tx.customer_id
        db.delete(tx)
        db.commit()
        return RedirectResponse(f"/esk/customers/edit/{customer_id}", status_code=302)
    
    return RedirectResponse("/esk/customers", status_code=302)


# =========================================================
# SUPPLIERS
# =========================================================

@router.get("/esk/suppliers", response_class=HTMLResponse)
def suppliers_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    from datetime import timedelta
    suppliers  = db.query(Supplier).order_by(Supplier.created_at.desc()).all()
    week_ago   = datetime.utcnow() - timedelta(days=7)
    weekly_new  = sum(1 for s in suppliers if s.created_at and s.created_at >= week_ago)
    city_count  = len(set(s.city for s in suppliers if s.city))

    # Her tedarikçi için cari bakiye hesapla
    supplier_balances = {}
    for supplier in suppliers:
        balance_data = _calculate_account_balance(db, supplier_id=supplier.id)
        dom = balance_data["dominant_currency"]
        nb  = balance_data["native_balances"]
        supplier_balances[supplier.id] = {
            "balance_usd":        balance_data["balance_usd"],
            "dominant_currency":  dom,
            "native_balance":     nb.get(dom, 0),
        }

    return templates.TemplateResponse("admin_suppliers.html", {
        "request": request,
        "suppliers": suppliers,
        "weekly_new": weekly_new,
        "city_count": city_count,
        "supplier_balances": supplier_balances,
    })


@router.post("/esk/suppliers/create")
def create_supplier(
    name: str = Form(...),
    contact_person: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    tax_id: str = Form(""),
    billing_address: str = Form(""),
    city: str = Form(""),
    district: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    db.add(Supplier(
        name=name,
        contact_person=contact_person or None,
        email=email or None,
        phone=phone or None,
        tax_id=tax_id or None,
        billing_address=billing_address or None,
        city=city or None,
        district=district or None,
        notes=notes or None,
    ))
    db.commit()
    return RedirectResponse("/esk/suppliers", status_code=302)


@router.get("/esk/suppliers/edit/{supplier_id}", response_class=HTMLResponse)
def edit_supplier_page(
    supplier_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        return RedirectResponse("/esk/suppliers", status_code=302)

    # Cari hesap bakiyesi hesapla
    account_data = _calculate_account_balance(db, supplier_id=supplier_id)

    rates = get_rates()
    dom  = account_data["dominant_currency"]
    nb   = account_data["native_balances"]
    native = account_data["native"]

    return templates.TemplateResponse("admin_suppliers_edit.html", {
        "request":              request,
        "supplier":             supplier,
        "account_balance":      account_data["balance_usd"],
        "account_transactions": account_data["transactions"],
        "total_debit":          account_data["total_debit_usd"],
        "total_credit":         account_data["total_credit_usd"],
        "dominant_currency":    dom,
        "native_balances":      nb,
        "native_totals":        native,
        "rates":                rates,
    })


@router.post("/esk/suppliers/update/{supplier_id}")
def update_supplier(
    supplier_id: int,
    name: str = Form(...),
    contact_person: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    tax_id: str = Form(""),
    billing_address: str = Form(""),
    city: str = Form(""),
    district: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier:
        supplier.name            = name
        supplier.contact_person  = contact_person or None
        supplier.email           = email or None
        supplier.phone           = phone or None
        supplier.tax_id          = tax_id or None
        supplier.billing_address = billing_address or None
        supplier.city            = city or None
        supplier.district        = district or None
        supplier.notes           = notes or None
        db.commit()
    return RedirectResponse(f"/esk/suppliers/edit/{supplier_id}", status_code=302)


@router.post("/esk/suppliers/delete/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier:
        db.delete(supplier)
        db.commit()
    return RedirectResponse("/esk/suppliers", status_code=302)


@router.post("/esk/suppliers/{supplier_id}/account/add")
def add_supplier_account_transaction(
    supplier_id: int,
    type: str = Form(...),
    amount: float = Form(...),
    currency: str = Form("USD"),
    description: str = Form(""),
    reference_no: str = Form(""),
    transaction_date: str = Form(""),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    # Tarih parse
    tx_date = datetime.utcnow()
    if transaction_date:
        try:
            tx_date = datetime.strptime(transaction_date, "%Y-%m-%dT%H:%M") - _timedelta(hours=3)
        except ValueError:
            pass

    tx = AccountTransaction(
        type=type,
        amount=amount,
        currency=currency,
        description=description or None,
        reference_no=reference_no or None,
        supplier_id=supplier_id,
        transaction_date=tx_date,
    )
    db.add(tx)
    db.commit()
    
    return RedirectResponse(f"/esk/suppliers/edit/{supplier_id}", status_code=302)


@router.post("/esk/suppliers/account/delete/{tx_id}")
def delete_supplier_account_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    tx = db.query(AccountTransaction).filter(AccountTransaction.id == tx_id).first()
    if tx and tx.supplier_id:
        supplier_id = tx.supplier_id
        db.delete(tx)
        db.commit()
        return RedirectResponse(f"/esk/suppliers/edit/{supplier_id}", status_code=302)
    
    return RedirectResponse("/esk/suppliers", status_code=302)


# =========================================================
# REQUESTS (Teklif Talepleri)
# =========================================================

@router.get("/esk/requests", response_class=HTMLResponse)
def requests_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    import json
    rates = get_rates()
    # Reverse map: currency code → a representative lang for format_price
    _CURRENCY_LANG = {v: k for k, v in LANG_CURRENCY.items()}  # USD→en, TRY→tr, EUR→de
    quote_requests = db.query(QuoteRequest).order_by(QuoteRequest.created_at.desc()).all()
    for req in quote_requests:
        try:
            req.items_data = json.loads(req.cart_data) if req.cart_data else []
        except Exception:
            req.items_data = []
        lang_for_fmt = _CURRENCY_LANG.get(req.currency or "USD", "en")
        req.price_display = format_price(req.total_price, lang_for_fmt, rates)

    return templates.TemplateResponse("admin_requests.html", {
        "request": request, "requests": quote_requests
    })


@router.post("/esk/requests/approve/{req_id}")
def approve_request(
    req_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    quote = db.query(QuoteRequest).filter(QuoteRequest.id == req_id).first()
    if quote:
        # Müşteri olarak kaydet (aynı e-posta yoksa)
        existing = db.query(Customer).filter(Customer.email == quote.email).first()
        if not existing:
            db.add(Customer(
                name=quote.company_name,
                email=quote.email,
                phone=quote.phone,
                contact_person=quote.contact_person,
                country=quote.country,
            ))
        db.delete(quote)
        db.commit()
    return RedirectResponse("/esk/requests", status_code=302)


@router.post("/esk/requests/delete/{req_id}")
def delete_request(
    req_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    quote = db.query(QuoteRequest).filter(QuoteRequest.id == req_id).first()
    if quote:
        db.delete(quote)
        db.commit()
    return RedirectResponse("/esk/requests", status_code=302)




# =========================================================
# FINANCE
# =========================================================

@router.get("/esk/finance", response_class=HTMLResponse)
def finance_page(
    request: Request,
    period: str = "month",
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    from datetime import timedelta, date
    import calendar

    now = datetime.utcnow()

    # Periyoda göre başlangıç tarihi
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "quarter":
        start = (now - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # all
        start = datetime(2000, 1, 1)

    txs = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.transaction_date >= start)
        .order_by(FinanceTransaction.transaction_date.desc())
        .all()
    )

    # Tüm tutarları USD'ye çevir
    total_income_usd     = 0.0
    total_expense_usd    = 0.0
    official_income_usd  = 0.0
    official_expense_usd = 0.0
    personal_income_usd  = 0.0
    personal_expense_usd = 0.0
    transfer_count       = 0

    for tx in txs:
        amount_usd = _convert_to_usd(tx.amount, tx.currency or "TRY")
        src = getattr(tx, "account_source", "official") or "official"
        is_transfer = getattr(tx, "is_transfer", 0)

        if is_transfer:
            # Transfer: genel toplama dahil değil, ama hesap bazlı bakiyeyi etkiler
            transfer_count += 1
            if tx.type == "income":   # hedefe giriş
                if src == "personal":
                    personal_income_usd += amount_usd
                else:
                    official_income_usd += amount_usd
            else:                      # kaynaktan çıkış
                if src == "personal":
                    personal_expense_usd += amount_usd
                else:
                    official_expense_usd += amount_usd
        else:
            # Normal işlem: hem genel hem hesap bazlı toplamlara dahil
            if tx.type == "income":
                total_income_usd += amount_usd
                if src == "personal":
                    personal_income_usd += amount_usd
                else:
                    official_income_usd += amount_usd
            else:
                total_expense_usd += amount_usd
                if src == "personal":
                    personal_expense_usd += amount_usd
                else:
                    official_expense_usd += amount_usd

    net_balance   = total_income_usd    - total_expense_usd
    official_net  = official_income_usd - official_expense_usd
    personal_net  = personal_income_usd - personal_expense_usd
    income_count  = sum(1 for t in txs if t.type == "income" and not getattr(t, "is_transfer", 0))
    expense_count = sum(1 for t in txs if t.type == "expense" and not getattr(t, "is_transfer", 0))
    total_count   = len(txs)

    # Son 6 ay baz alarak aylık grafik verisi (periyottan bağımsız)
    monthly_data = []
    for i in range(5, -1, -1):
        m_date  = (now.replace(day=1) - timedelta(days=i*28)).replace(day=1)
        m_year  = m_date.year
        m_month = m_date.month
        m_last  = calendar.monthrange(m_year, m_month)[1]
        m_start = datetime(m_year, m_month, 1)
        m_end   = datetime(m_year, m_month, m_last, 23, 59, 59)
        m_txs   = db.query(FinanceTransaction).filter(
            FinanceTransaction.transaction_date >= m_start,
            FinanceTransaction.transaction_date <= m_end
        ).all()
        
        # Aylık verileri de USD'ye çevir
        month_income_usd = 0.0
        month_expense_usd = 0.0
        for tx in m_txs:
            amount_usd = _convert_to_usd(tx.amount, tx.currency or "TRY")
            if tx.type == "income":
                month_income_usd += amount_usd
            else:
                month_expense_usd += amount_usd
        
        monthly_data.append({
            "month":   m_date.strftime("%b"),
            "income":  month_income_usd,
            "expense": month_expense_usd,
        })

    customers = db.query(Customer).order_by(Customer.name).all()
    suppliers = db.query(Supplier).order_by(Supplier.name).all()
    tr_tz     = timezone(_timedelta(hours=3))
    now_tr    = now.replace(tzinfo=timezone.utc).astimezone(tr_tz)
    now_str   = now_tr.strftime("%Y-%m-%dT%H:%M")

    return templates.TemplateResponse("admin_finance.html", {
        "request":            request,
        "period":             period,
        "transactions":       txs,
        "total_income":       total_income_usd,
        "total_expense":      total_expense_usd,
        "net_balance":        net_balance,
        "official_income":    official_income_usd,
        "official_expense":   official_expense_usd,
        "official_net":       official_net,
        "personal_income":    personal_income_usd,
        "personal_expense":   personal_expense_usd,
        "personal_net":       personal_net,
        "income_count":       income_count,
        "expense_count":      expense_count,
        "total_count":        total_count,
        "transfer_count":     transfer_count,
        "monthly_data":       monthly_data,
        "customers":          customers,
        "suppliers":          suppliers,
        "now_str":            now_str,
        "rates":              get_rates(),
    })


@router.post("/esk/finance/create")
def create_transaction(
    request: Request,
    type:             str  = Form(...),
    amount:           float = Form(...),
    currency:         str  = Form("TRY"),
    category:         str  = Form(""),
    transaction_date: str  = Form(""),
    description:      str  = Form(""),
    reference_no:     str  = Form(""),
    party_type:       str  = Form(""),
    customer_id:      str  = Form(""),
    supplier_id:      str  = Form(""),
    account_source:   str  = Form("official"),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    # Tarih parse
    tx_date = datetime.utcnow()
    if transaction_date:
        try:
            tx_date = datetime.strptime(transaction_date, "%Y-%m-%dT%H:%M") - _timedelta(hours=3)
        except ValueError:
            pass

    cid = int(customer_id) if customer_id and party_type == "customer" else None
    sid = int(supplier_id) if supplier_id and party_type == "supplier" else None

    tx = FinanceTransaction(
        type=type,
        amount=amount,
        currency=currency,
        category=category or None,
        account_source=account_source if account_source in ("official", "personal") else "official",
        transaction_date=tx_date,
        description=description or None,
        reference_no=reference_no or None,
        customer_id=cid,
        supplier_id=sid,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    # Müşteri/Tedarikçi ile ilişkiliyse cari hesaba otomatik kaydet
    if cid or sid:
        # MÜŞTERİ İÇİN:
        #   income (gelir)  = müşteriden tahsilat yaptık  → credit (müşteri borcu azalır)
        #   expense (gider) = müşteriye iade/ödeme yaptık → debit  (müşteri borcu artar)
        # TEDARİKÇİ İÇİN:
        #   income (gelir)  = tedarikçiden iade aldık     → debit  (bizim borcumuz azalır)
        #   expense (gider) = tedarikçiye ödeme yaptık    → debit  (bizim borcumuz azalır)

        if cid:  # Müşteri
            if type == "income":
                account_type = "credit"  # Tahsilat = müşteri borcu azalır
                desc_prefix = "Tahsilat"
            else:  # expense
                account_type = "debit"   # Müşteriye ödeme/iade = müşteri borcu artar
                desc_prefix = "İade/Ödeme"
        else:  # Tedarikçi
            if type == "income":
                account_type = "debit"   # Tedarikçiden iade = bizim borcumuz azalır
                desc_prefix = "İade/Gelir"
            else:  # expense
                account_type = "debit"   # Tedarikçiye ödeme = bizim borcumuz azalır
                desc_prefix = "Ödeme"

        account_tx = AccountTransaction(
            type=account_type,
            amount=amount,
            currency=currency,
            description=f"{desc_prefix}: {description or category or 'Finans İşlemi'}",
            reference_no=reference_no,
            customer_id=cid,
            supplier_id=sid,
            finance_transaction_id=tx.id,
            transaction_date=tx_date,
        )
        db.add(account_tx)
        db.commit()
    
    return RedirectResponse("/esk/finance", status_code=302)



@router.post("/esk/finance/transfer")
def create_transfer(
    request: Request,
    amount:           float = Form(...),
    currency:         str   = Form("TRY"),
    from_source:      str   = Form(...),   # "official" veya "personal"
    to_source:        str   = Form(...),   # "official" veya "personal"
    description:      str   = Form(""),
    transaction_date: str   = Form(""),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    """Hesaplar arası transfer: çift kayıt yazar ve birbirine bağlar."""
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    tx_date = datetime.utcnow()
    if transaction_date:
        try:
            tx_date = datetime.strptime(transaction_date, "%Y-%m-%dT%H:%M") - _timedelta(hours=3)
        except ValueError:
            pass

    desc = description or f"{('Resmi' if from_source == 'official' else 'Şahsi')} → {('Resmi' if to_source == 'official' else 'Şahsi')} Transfer"

    # Kaynak hesaptan çıkış (expense)
    tx_out = FinanceTransaction(
        type="expense",
        amount=amount,
        currency=currency,
        category="Hesaplar Arası Transfer",
        account_source=from_source,
        is_transfer=1,
        description=desc,
        transaction_date=tx_date,
    )
    db.add(tx_out)
    db.flush()  # id al

    # Hedef hesaba giriş (income)
    tx_in = FinanceTransaction(
        type="income",
        amount=amount,
        currency=currency,
        category="Hesaplar Arası Transfer",
        account_source=to_source,
        is_transfer=1,
        description=desc,
        transaction_date=tx_date,
        transfer_pair_id=tx_out.id,
    )
    db.add(tx_in)
    db.flush()

    # Karşı kayıtların pair_id'lerini birbirine bağla
    tx_out.transfer_pair_id = tx_in.id
    db.commit()

    return RedirectResponse("/esk/finance", status_code=302)

@router.post("/esk/finance/delete/{tx_id}")
def delete_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required)
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)

    tx = db.query(FinanceTransaction).filter(FinanceTransaction.id == tx_id).first()
    if tx:
        db.delete(tx)
        db.commit()
    return RedirectResponse("/esk/finance", status_code=302)

# =========================================================
# CMS — MEDYA YÜKLEME (TinyMCE için)
# =========================================================

@router.post("/esk/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    """TinyMCE editörü için görsel yükleme endpoint'i."""
    if not admin:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    import uuid, mimetypes
    allowed = {"image/jpeg", "image/png", "image/jpg"}
    ct = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if ct not in allowed:
        return JSONResponse({"error": "Geçersiz dosya türü (sadece JPG/JPEG/PNG)"}, status_code=400)

    if _is_jpeg_jpg_png_upload(file):
        try:
            optimized_fname = await optimize_and_save_image(file, UPLOAD_DIR_IMAGES)
        except ValueError as e:
            if "too large" in str(e).lower():
                return JSONResponse({"error": "Dosya çok büyük (max 5MB)"}, status_code=413)
            return JSONResponse({"error": "Dosya işlenemedi"}, status_code=400)
        return JSONResponse({"location": f"/static/upload/images/{optimized_fname}"})

    ext = os.path.splitext(file.filename or "img")[1] or ".jpg"
    ext = ext.lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".jpg"
    fname = f"media_{uuid.uuid4().hex[:12]}{ext}"
    path = os.path.join(UPLOAD_DIR_IMAGES, fname)
    with open(path, "wb") as f:
        f.write(await file.read())
    return JSONResponse({"location": f"/static/upload/images/{fname}"})


@router.post("/esk/upload-homepage-image")
async def upload_homepage_image(
    file: UploadFile = File(...),
    admin: str = Depends(admin_required),
):
    """Anasayfa düzenleyicide PC'den görsel yükler; static/upload/images'a kaydeder."""
    if not admin:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    import uuid
    import mimetypes
    allowed = {"image/jpeg", "image/png", "image/jpg"}
    ct = file.content_type or (mimetypes.guess_type(file.filename or "")[0] if file.filename else "")
    if ct not in allowed:
        return JSONResponse({"error": "Sadece JPG/JPEG/PNG yükleyebilirsiniz."}, status_code=400)

    if _is_jpeg_jpg_png_upload(file):
        try:
            optimized_fname = await optimize_and_save_image(file, IMAGES_DIR)
        except ValueError as e:
            if "too large" in str(e).lower():
                return JSONResponse({"error": "Dosya çok büyük (max 5MB)"}, status_code=413)
            return JSONResponse({"error": "Dosya işlenemedi"}, status_code=400)
        url = f"/static/upload/images/{optimized_fname}"
        return JSONResponse({"url": url, "location": url})

    ext = os.path.splitext(file.filename or "img")[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".jpg"
    fname = f"hp_{uuid.uuid4().hex[:10]}{ext}"
    path = os.path.join(IMAGES_DIR, fname)
    with open(path, "wb") as f:
        f.write(await file.read())
    url = f"/static/upload/images/{fname}"
    return JSONResponse({"url": url, "location": url})


# =========================================================
# MEDYA KÜTÜPHANESİ
# =========================================================

# Desteklenen dosya türleri ve kategorileri
_MEDIA_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}
_MEDIA_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
_MEDIA_DOC_EXTS   = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"}

# Maksimum yüklenebilir dosya boyutu (50 MB)
_MEDIA_MAX_SIZE_BYTES = 50 * 1024 * 1024


def _list_media_files() -> list[dict]:
    """
    Üç upload klasöründeki tüm dosyaları tarayıp metadata listesi döner.
    Her öğe: {name, url, path, size, size_str, ext, media_type, modified}
    """
    klasorler = [
        (UPLOAD_DIR_IMAGES, "/static/upload/images"),
        (UPLOAD_DIR_VIDEOS, "/static/upload/videos"),
        (UPLOAD_DIR_DOCS,   "/static/upload/doc"),
    ]
    dosyalar = []
    for dizin, url_prefix in klasorler:
        if not os.path.isdir(dizin):
            continue
        for dosya_adi in os.listdir(dizin):
            tam_yol = os.path.join(dizin, dosya_adi)
            if not os.path.isfile(tam_yol):
                continue
            ext = os.path.splitext(dosya_adi)[1].lower()
            # Medya türünü belirle
            if ext in _MEDIA_IMAGE_EXTS:
                media_type = "image"
            elif ext in _MEDIA_VIDEO_EXTS:
                media_type = "video"
            elif ext in _MEDIA_DOC_EXTS:
                media_type = "doc"
            else:
                media_type = "other"

            boyut = os.path.getsize(tam_yol)
            # Okunabilir boyut formatı
            if boyut < 1024:
                boyut_str = f"{boyut} B"
            elif boyut < 1024 * 1024:
                boyut_str = f"{boyut / 1024:.1f} KB"
            else:
                boyut_str = f"{boyut / (1024*1024):.1f} MB"

            degistirme = datetime.fromtimestamp(os.path.getmtime(tam_yol))
            dosyalar.append({
                "name": dosya_adi,
                "url": f"{url_prefix}/{dosya_adi}",
                "dir": dizin,
                "size": boyut,
                "size_str": boyut_str,
                "ext": ext.lstrip(".").upper(),
                "media_type": media_type,
                "modified": degistirme.strftime("%d.%m.%Y %H:%M"),
            })

    # En yeni dosyalar önce
    dosyalar.sort(key=lambda x: x["modified"], reverse=True)
    return dosyalar


@router.get("/esk/media", response_class=HTMLResponse)
async def media_library(
    request: Request,
    tip: str = "all",
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    """Medya kütüphanesi: tüm upload dosyalarını listeler."""
    if not admin:
        return RedirectResponse("/esk/login", status_code=303)

    dosyalar = _list_media_files()

    # Filtrele
    if tip in ("image", "video", "doc"):
        filtreli = [d for d in dosyalar if d["media_type"] == tip]
    else:
        filtreli = dosyalar

    # Sayım
    sayimlar = {
        "all":   len(dosyalar),
        "image": sum(1 for d in dosyalar if d["media_type"] == "image"),
        "video": sum(1 for d in dosyalar if d["media_type"] == "video"),
        "doc":   sum(1 for d in dosyalar if d["media_type"] == "doc"),
    }

    return templates.TemplateResponse("admin_media.html", {
        "request": request,
        "dosyalar": filtreli,
        "aktif_tip": tip,
        "sayimlar": sayimlar,
    })


@router.post("/esk/media/upload")
async def media_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    admin: str = Depends(admin_required),
):
    """Medya kütüphanesine yeni dosya(lar) yükler."""
    if not admin:
        return JSONResponse({"error": "Yetkisiz erişim"}, status_code=401)

    import uuid
    import mimetypes

    yuklenenler = []
    hatalar = []

    for file in files:
        icerik = await file.read()
        boyut = len(icerik)

        if boyut > _MEDIA_MAX_SIZE_BYTES:
            hatalar.append(f"{file.filename}: Dosya çok büyük (maks 50 MB)")
            continue

        ext = os.path.splitext(file.filename or "")[1].lower()
        if not ext:
            hatalar.append(f"{file.filename}: Geçersiz dosya uzantısı")
            continue

        # Hedef klasörü belirle
        if ext in _MEDIA_IMAGE_EXTS:
            hedef_dir = UPLOAD_DIR_IMAGES
            url_prefix = "/static/upload/images"
        elif ext in _MEDIA_VIDEO_EXTS:
            hedef_dir = UPLOAD_DIR_VIDEOS
            url_prefix = "/static/upload/videos"
        elif ext in _MEDIA_DOC_EXTS:
            hedef_dir = UPLOAD_DIR_DOCS
            url_prefix = "/static/upload/doc"
        else:
            hatalar.append(f"{file.filename}: Desteklenmeyen dosya türü")
            continue

        # JPG/JPEG/PNG → WebP dönüşümü; diğer dosyalar olduğu gibi kaydedilir
        if ext in (".jpg", ".jpeg", ".png") and hedef_dir == UPLOAD_DIR_IMAGES:
            from io import BytesIO
            from PIL import Image as _PilImage
            try:
                img = _PilImage.open(BytesIO(icerik))
                img.load()
                # Maksimum boyut 1200px (aspect ratio korunur)
                max_dim = 1200
                if img.width > max_dim or img.height > max_dim:
                    resample = _PilImage.Resampling.LANCZOS if hasattr(_PilImage, "Resampling") else _PilImage.LANCZOS
                    img.thumbnail((max_dim, max_dim), resample=resample)
                # Alfa kanalını beyaz arka plana yapıştır (WebP JPEG uyumlu)
                if img.mode in ("RGBA", "LA", "P"):
                    bg = _PilImage.new("RGB", img.size, (255, 255, 255))
                    alpha = img.convert("RGBA").split()[-1]
                    bg.paste(img.convert("RGB"), mask=alpha)
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                guvenli_ad = f"media_{uuid.uuid4().hex[:12]}.webp"
                tam_yol = os.path.join(hedef_dir, guvenli_ad)
                img.save(tam_yol, "WEBP", quality=75, optimize=True)
                print(f"[media_upload] WebP olarak kaydedildi: {guvenli_ad}")
            except Exception as e:
                # Dönüşüm başarısız olursa orijinal formatı kaydet
                guvenli_ad = f"media_{uuid.uuid4().hex[:12]}{ext}"
                tam_yol = os.path.join(hedef_dir, guvenli_ad)
                with open(tam_yol, "wb") as f:
                    f.write(icerik)
                print(f"[media_upload] WebP dönüşümü başarısız, ham kaydedildi: {guvenli_ad} ({e})")
        else:
            # Video, belge, SVG, GIF, zaten WebP olan dosyalar → olduğu gibi kaydet
            guvenli_ad = f"media_{uuid.uuid4().hex[:12]}{ext}"
            tam_yol = os.path.join(hedef_dir, guvenli_ad)
            with open(tam_yol, "wb") as f:
                f.write(icerik)

        yuklenenler.append({"name": guvenli_ad, "url": f"{url_prefix}/{guvenli_ad}"})

    return JSONResponse({
        "uploaded": yuklenenler,
        "errors": hatalar,
        "count": len(yuklenenler),
    })


@router.post("/esk/media/delete")
async def media_delete(
    request: Request,
    admin: str = Depends(admin_required),
):
    """Medya kütüphanesinden dosya siler (sunucudan da kaldırır)."""
    if not admin:
        return JSONResponse({"error": "Yetkisiz erişim"}, status_code=401)

    veri = await request.json()
    dosya_adi = veri.get("name", "").strip()

    if not dosya_adi:
        return JSONResponse({"error": "Dosya adı gerekli"}, status_code=400)

    # Path traversal saldırısını önle: sadece dosya adına izin ver
    if "/" in dosya_adi or "\\" in dosya_adi or ".." in dosya_adi:
        return JSONResponse({"error": "Geçersiz dosya adı"}, status_code=400)

    # Üç klasörde ara ve sil
    for dizin in (UPLOAD_DIR_IMAGES, UPLOAD_DIR_VIDEOS, UPLOAD_DIR_DOCS):
        tam_yol = os.path.join(dizin, dosya_adi)
        if os.path.isfile(tam_yol):
            os.remove(tam_yol)
            return JSONResponse({"ok": True, "deleted": dosya_adi})

    return JSONResponse({"error": "Dosya bulunamadı"}, status_code=404)


# =========================================================
# CMS — SITE AYARLARI (Logo, Favicon, İletişim, Sosyal)
# =========================================================

def _settings_i18n_seed(s):
    """Mevcut (legacy) kolonlardan i18n için 'en' verisi üretir."""
    import json
    data = (s.get_i18n_data() if s and getattr(s, "get_i18n_data", None) else {}) or {}
    if not data or "en" not in data:
        fc_raw = getattr(s, "footer_columns", None)
        try:
            fc = json.loads(fc_raw) if isinstance(fc_raw, str) and fc_raw else []
        except Exception:
            fc = []
        en = {
            "site_name": getattr(s, "site_name", None) or "Heni",
            "contact_email": getattr(s, "contact_email", None) or "",
            "contact_phone": getattr(s, "contact_phone", None) or "",
            "contact_address": getattr(s, "contact_address", None) or "",
            "seo_title_template": getattr(s, "seo_title_template", None) or "",
            "seo_description": getattr(s, "seo_description", None) or "",
            "footer_description": getattr(s, "footer_description", None) or "",
            "footer_copyright_lead": getattr(s, "footer_copyright_lead", None) or "",
            "footer_copyright": getattr(s, "footer_copyright", None) or "",
            "footer_columns": fc,
        }
        if not data:
            data = {}
        data["en"] = en
    return data


@router.get("/esk/settings")
def settings_get(request: Request, db: Session = Depends(get_db), admin: str = Depends(admin_required)):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    s = db.query(SiteSettings).filter(SiteSettings.id == 1).first()
    if not s:
        s = SiteSettings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    i18n = _settings_i18n_seed(s)
    return templates.TemplateResponse("admin_settings.html", {
        "request": request,
        "s": s,
        "i18n": i18n,
        "supported_langs": SUPPORTED_LANGS,
        "lang_labels": LANG_LABELS,
    })


@router.post("/esk/settings")
async def settings_post(
    request: Request,
    i18n_json: str = Form("{}"),
    social_linkedin: str = Form(""),
    social_instagram: str = Form(""),
    social_twitter: str = Form(""),
    social_whatsapp: str = Form(""),
    analytics_code: str = Form(""),
    custom_css: str = Form(""),
    logo: UploadFile = File(None),
    logo_white: UploadFile = File(None),
    favicon: UploadFile = File(None),
    footer_bg_image: UploadFile = File(None),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    import json
    s = db.query(SiteSettings).filter(SiteSettings.id == 1).first()
    if not s:
        s = SiteSettings(id=1)
        db.add(s)

    try:
        parsed = json.loads(i18n_json) if i18n_json else {}
        if isinstance(parsed, dict):
            s.i18n = json.dumps(parsed)
    except Exception:
        pass
    s.social_linkedin    = social_linkedin
    s.social_instagram  = social_instagram
    s.social_twitter     = social_twitter
    s.social_whatsapp    = social_whatsapp
    s.analytics_code     = analytics_code
    s.custom_css         = custom_css

    if logo and logo.filename:
        os.makedirs(UPLOAD_DIR_IMAGES, exist_ok=True)
        if _is_jpeg_jpg_png_upload(logo):
            try:
                optimized_fname = await optimize_and_save_image(logo, UPLOAD_DIR_IMAGES, is_logo=True)
                s.logo_url = f"/static/upload/images/{optimized_fname}"
            except ValueError as e:
                if "too large" in str(e).lower():
                    return RedirectResponse("/esk/settings?error=image_too_large", status_code=302)
                return RedirectResponse("/esk/settings?saved=0", status_code=302)
        else:
            ext = os.path.splitext(logo.filename)[1]
            fname = f"logo{ext}"
            path = os.path.join(UPLOAD_DIR_IMAGES, fname)
            with open(path, "wb") as f:
                f.write(await logo.read())
            s.logo_url = f"/static/upload/images/{fname}"

    if logo_white and logo_white.filename:
        os.makedirs(UPLOAD_DIR_IMAGES, exist_ok=True)
        if _is_jpeg_jpg_png_upload(logo_white):
            try:
                optimized_fname = await optimize_and_save_image(logo_white, UPLOAD_DIR_IMAGES, is_logo=True)
                s.logo_white_url = f"/static/upload/images/{optimized_fname}"
            except ValueError as e:
                if "too large" in str(e).lower():
                    return RedirectResponse("/esk/settings?error=image_too_large", status_code=302)
                return RedirectResponse("/esk/settings?saved=0", status_code=302)
        else:
            ext = os.path.splitext(logo_white.filename)[1]
            fname = f"logo_white{ext}"
            path = os.path.join(UPLOAD_DIR_IMAGES, fname)
            with open(path, "wb") as f:
                f.write(await logo_white.read())
            s.logo_white_url = f"/static/upload/images/{fname}"

    if favicon and favicon.filename:
        os.makedirs(UPLOAD_DIR_IMAGES, exist_ok=True)
        if _is_jpeg_jpg_png_upload(favicon):
            try:
                optimized_fname = await optimize_and_save_image(favicon, UPLOAD_DIR_IMAGES, is_logo=True)
                s.favicon_url = f"/static/upload/images/{optimized_fname}"
            except ValueError as e:
                if "too large" in str(e).lower():
                    return RedirectResponse("/esk/settings?error=image_too_large", status_code=302)
                return RedirectResponse("/esk/settings?saved=0", status_code=302)
        else:
            ext = os.path.splitext(favicon.filename)[1]
            fname = f"favicon{ext}"
            path = os.path.join(UPLOAD_DIR_IMAGES, fname)
            with open(path, "wb") as f:
                f.write(await favicon.read())
            s.favicon_url = f"/static/upload/images/{fname}"

    # Footer arka plan görseli yükleme (tüm dillere global uygulanır)
    if footer_bg_image and footer_bg_image.filename:
        os.makedirs(UPLOAD_DIR_IMAGES, exist_ok=True)
        if _is_jpeg_jpg_png_upload(footer_bg_image):
            try:
                optimized_fname = await optimize_and_save_image(footer_bg_image, UPLOAD_DIR_IMAGES)
                s.footer_bg_image_url = f"/static/upload/images/{optimized_fname}"
            except ValueError as e:
                if "too large" in str(e).lower():
                    return RedirectResponse("/esk/settings?error=image_too_large", status_code=302)
                return RedirectResponse("/esk/settings?saved=0", status_code=302)
        else:
            ext = os.path.splitext(footer_bg_image.filename)[1]
            fname = f"footer_bg{ext}"
            path = os.path.join(UPLOAD_DIR_IMAGES, fname)
            with open(path, "wb") as f:
                f.write(await footer_bg_image.read())
            s.footer_bg_image_url = f"/static/upload/images/{fname}"

    db.commit()
    return RedirectResponse("/esk/settings?saved=1", status_code=302)


# =========================================================
# CMS — SAYFALAR LİSTESİ
# =========================================================

@router.get("/esk/pages")
def pages_list(request: Request, db: Session = Depends(get_db), admin: str = Depends(admin_required)):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    pages = db.query(Page).order_by(Page.sort_order, Page.id).all()
    return templates.TemplateResponse("admin_pages.html", {
        "request": request,
        "pages": pages,
        "langs": SUPPORTED_LANGS,
        "lang_labels": LANG_LABELS,
    })


@router.post("/esk/pages/new")
def page_new(
    request: Request,
    slug: str = Form(...),
    template: str = Form("page_generic.html"),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    existing = db.query(Page).filter(Page.slug == slug).first()
    if existing:
        return RedirectResponse(f"/esk/pages/{existing.id}/edit?error=slug_exists", status_code=302)
    page = Page(slug=slug, template=template)
    db.add(page)
    db.flush()
    # EN başlangıç çevirisi oluştur
    trans = PageTranslation(page_id=page.id, lang="en", slug=slug, title=slug.replace("-", " ").title())
    db.add(trans)
    db.commit()
    return RedirectResponse(f"/esk/pages/{page.id}/edit", status_code=302)


@router.post("/esk/pages/{page_id}/delete")
def page_delete(page_id: int, db: Session = Depends(get_db), admin: str = Depends(admin_required)):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    page = db.query(Page).filter(Page.id == page_id).first()
    if page:
        db.delete(page)
        db.commit()
    return RedirectResponse("/esk/pages", status_code=302)


# =========================================================
# CMS — SAYFA DÜZENLEME (çok dilli + FAQ)
# =========================================================

@router.get("/esk/pages/{page_id}/edit")
def page_edit_get(
    page_id: int,
    lang: str = "en",
    request: Request = None,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        return RedirectResponse("/esk/pages", status_code=302)
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    trans = next((t for t in page.translations if t.lang == lang), None)
    faqs = [f for f in page.faqs if f.lang == lang]
    faqs.sort(key=lambda x: x.sort_order)
    return templates.TemplateResponse("admin_page_edit.html", {
        "request": request,
        "page": page,
        "trans": trans,
        "faqs": faqs,
        "active_lang": lang,
        "langs": SUPPORTED_LANGS,
        "lang_labels": LANG_LABELS,
    })


@router.post("/esk/pages/{page_id}/edit")
def page_edit_post(
    page_id: int,
    request: Request,
    lang: str = Form("en"),
    slug: str = Form(""),
    title: str = Form(""),
    body: str = Form(""),
    meta_title: str = Form(""),
    meta_description: str = Form(""),
    og_title: str = Form(""),
    og_description: str = Form(""),
    is_published: int = Form(1),
    show_in_nav: int = Form(0),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        return RedirectResponse("/esk/pages", status_code=302)

    page.is_published = is_published
    page.show_in_nav  = show_in_nav
    page.sort_order   = sort_order

    # EN ise master slug'ı da güncelle
    if lang == "en" and slug:
        page.slug = slug

    # Translation upsert
    trans = next((t for t in page.translations if t.lang == lang), None)
    if not trans:
        trans = PageTranslation(page_id=page.id, lang=lang)
        db.add(trans)
    trans.slug             = slug or page.slug
    trans.title            = title
    trans.body             = body
    trans.meta_title       = meta_title
    trans.meta_description = meta_description
    trans.og_title         = og_title
    trans.og_description   = og_description

    db.commit()
    return RedirectResponse(f"/esk/pages/{page_id}/edit?lang={lang}&saved=1", status_code=302)


# =========================================================
# CMS — FAQ CRUD (sayfa + dil bazlı)
# =========================================================

@router.post("/esk/pages/{page_id}/faq/add")
def faq_add(
    page_id: int,
    lang: str = Form("en"),
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    faq = FaqItem(
        page_id=page_id, lang=lang,
        question=question, answer=answer, sort_order=sort_order,
    )
    db.add(faq)
    db.commit()
    return RedirectResponse(f"/esk/pages/{page_id}/edit?lang={lang}&tab=faq", status_code=302)


@router.post("/esk/pages/{page_id}/faq/{faq_id}/edit")
def faq_edit(
    page_id: int,
    faq_id: int,
    lang: str = Form("en"),
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    faq = db.query(FaqItem).filter(FaqItem.id == faq_id, FaqItem.page_id == page_id).first()
    if faq:
        faq.question   = question
        faq.answer     = answer
        faq.sort_order = sort_order
        db.commit()
    return RedirectResponse(f"/esk/pages/{page_id}/edit?lang={lang}&tab=faq", status_code=302)


@router.post("/esk/pages/{page_id}/faq/{faq_id}/delete")
def faq_delete(
    page_id: int,
    faq_id: int,
    lang: str = Form("en"),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    faq = db.query(FaqItem).filter(FaqItem.id == faq_id, FaqItem.page_id == page_id).first()
    if faq:
        db.delete(faq)
        db.commit()
    return RedirectResponse(f"/esk/pages/{page_id}/edit?lang={lang}&tab=faq", status_code=302)


# =========================================================
# KATEGORİ İÇERİK YÖNETİMİ
# =========================================================

@router.get("/esk/categories")
def admin_categories(
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    from .routes_showroom import CATEGORY_SLUGS, CATEGORY_LABELS
    cats = db.query(CategoryContent).order_by(CategoryContent.sort_order, CategoryContent.id).all()
    # Henüz DB'de olmayan kategorileri oluştur
    existing_keys = {c.category_key for c in cats}
    for cat_key, cat_slug in CATEGORY_SLUGS.items():
        if cat_key not in existing_keys:
            cc = CategoryContent(category_key=cat_key, category_slug=cat_slug)
            db.add(cc)
    db.commit()
    cats = db.query(CategoryContent).order_by(CategoryContent.sort_order, CategoryContent.id).all()
    return templates.TemplateResponse("admin_categories.html", {
        "request":       request,
        "admin":         admin,
        "cats":          cats,
        "cat_labels":    CATEGORY_LABELS,
        "supported_langs": SUPPORTED_LANGS,
    })


@router.get("/esk/categories/{cat_id}/edit")
def admin_category_edit(
    cat_id: int,
    request: Request,
    lang: str = "tr",
    tab: str = "content",
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    from .routes_showroom import CATEGORY_LABELS
    cat = db.query(CategoryContent).filter(CategoryContent.id == cat_id).first()
    if not cat:
        return RedirectResponse("/esk/categories", status_code=302)
    trans = next((t for t in cat.translations if t.lang == lang), None)
    faqs  = [f for f in cat.faqs if f.lang == lang]
    faqs.sort(key=lambda x: x.sort_order)
    return templates.TemplateResponse("admin_category_edit.html", {
        "request":         request,
        "admin":           admin,
        "cat":             cat,
        "trans":           trans,
        "faqs":            faqs,
        "lang":            lang,
        "tab":             tab,
        "supported_langs": SUPPORTED_LANGS,
        "lang_labels":     LANG_LABELS,
        "cat_labels":      CATEGORY_LABELS,
    })


@router.post("/esk/categories/{cat_id}/save")
def admin_category_save(
    cat_id: int,
    lang: str = Form("tr"),
    tab: str = Form("content"),
    title: str = Form(""),
    intro: str = Form(""),
    body: str = Form(""),
    meta_title: str = Form(""),
    meta_description: str = Form(""),
    og_title: str = Form(""),
    og_description: str = Form(""),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    cat = db.query(CategoryContent).filter(CategoryContent.id == cat_id).first()
    if not cat:
        return RedirectResponse("/esk/categories", status_code=302)
    trans = next((t for t in cat.translations if t.lang == lang), None)
    if not trans:
        trans = CategoryTranslation(category_id=cat_id, lang=lang)
        db.add(trans)
    trans.title            = title or None
    trans.intro            = intro or None
    trans.body             = body or None
    trans.meta_title       = meta_title or None
    trans.meta_description = meta_description or None
    trans.og_title         = og_title or None
    trans.og_description   = og_description or None
    cat.updated_at         = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/esk/categories/{cat_id}/edit?lang={lang}&tab={tab}", status_code=302)


@router.post("/esk/categories/{cat_id}/faq/add")
def admin_category_faq_add(
    cat_id: int,
    lang: str = Form("tr"),
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    faq = CategoryFaq(
        category_id=cat_id, lang=lang,
        question=question, answer=answer, sort_order=sort_order,
    )
    db.add(faq)
    db.commit()
    return RedirectResponse(f"/esk/categories/{cat_id}/edit?lang={lang}&tab=faq", status_code=302)


@router.post("/esk/categories/{cat_id}/faq/{faq_id}/edit")
def admin_category_faq_edit(
    cat_id: int,
    faq_id: int,
    lang: str = Form("tr"),
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    faq = db.query(CategoryFaq).filter(CategoryFaq.id == faq_id, CategoryFaq.category_id == cat_id).first()
    if faq:
        faq.question   = question
        faq.answer     = answer
        faq.sort_order = sort_order
        db.commit()
    return RedirectResponse(f"/esk/categories/{cat_id}/edit?lang={lang}&tab=faq", status_code=302)


@router.post("/esk/categories/{cat_id}/faq/{faq_id}/delete")
def admin_category_faq_delete(
    cat_id: int,
    faq_id: int,
    lang: str = Form("tr"),
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    faq = db.query(CategoryFaq).filter(CategoryFaq.id == faq_id, CategoryFaq.category_id == cat_id).first()
    if faq:
        db.delete(faq)
        db.commit()
    return RedirectResponse(f"/esk/categories/{cat_id}/edit?lang={lang}&tab=faq", status_code=302)

# =========================================================
# ANASAYFA İÇERİK YÖNETİMİ
# =========================================================

import json as _json

# ─── Paylaşılan (dil-bağımsız) görsel alanları ───────────────────────────────
# Bu alanlardaki görseller tüm dillerde aynıdır.
# "tr" kaydı global görsel deposu görevi görür;
# diğer dillerde alan boşsa otomatik olarak "tr"'deki değer kullanılır.
SHARED_IMAGE_FIELDS = [
    "hero_image_url",
    "raw_materials_image_url",
    "private_label_image_url",
]
# services görselleri liste içinde saklandığından ayrı işlenir: svc1_image … svc4_image


def _get_shared_image(field: str, current_data: dict, db, lang: str) -> str:
    """
    Bir görsel alanı için değer döner.
    Önce mevcut dilin verisine bakar; boşsa 'tr' kaydından fallback yapar.
    """
    value = current_data.get(field, "")
    if value:
        return value
    if lang == "tr":
        return ""
    tr_hp = db.query(HomepageContent).filter(HomepageContent.lang == "tr").first()
    if not tr_hp:
        return ""
    return tr_hp.get_data().get(field, "")


def _get_shared_svc_image(idx: int, current_data: dict, db, lang: str) -> str:
    """services listesindeki idx. kartın görselini döner, boşsa tr'den fallback."""
    svcs = current_data.get("services", [])
    value = svcs[idx].get("image", "") if idx < len(svcs) else ""
    if value:
        return value
    if lang == "tr":
        return ""
    tr_hp = db.query(HomepageContent).filter(HomepageContent.lang == "tr").first()
    if not tr_hp:
        return ""
    tr_svcs = tr_hp.get_data().get("services", [])
    return tr_svcs[idx].get("image", "") if idx < len(tr_svcs) else ""


@router.get("/esk/homepage")
def admin_homepage(
    request: Request,
    lang: str = "tr",
    tab: str = "hero",
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    if tab not in ("hero", "services", "raw_materials", "private_label", "export", "certification", "nav", "cta", "seo"):
        return RedirectResponse(f"/esk/homepage?lang={lang}&tab=hero", status_code=302)
    hp = db.query(HomepageContent).filter(HomepageContent.lang == lang).first()
    if not hp:
        hp = HomepageContent(lang=lang)
        db.add(hp)
        db.commit()
    data = hp.get_data()

    # Her görsel alanı için "kendi değeri yoksa tr'deki" URL'yi hesapla.
    # Template bu dict'i hem önizleme hem de "kaynak yok" uyarısı için kullanır.
    shared_images: dict = {}
    for field in SHARED_IMAGE_FIELDS:
        shared_images[field] = _get_shared_image(field, data, db, lang)
    for i in range(4):
        shared_images[f"svc{i+1}_image"] = _get_shared_svc_image(i, data, db, lang)

    return templates.TemplateResponse("admin_homepage.html", {
        "request":         request,
        "admin":           admin,
        "hp":              hp,
        "data":            data,
        "lang":            lang,
        "tab":             tab,
        "supported_langs": SUPPORTED_LANGS,
        "lang_labels":     LANG_LABELS,
        "shared_images":   shared_images,   # fallback URL'leri
    })


@router.post("/esk/homepage/sync-image")
async def admin_homepage_sync_image(
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    """
    Belirtilen görsel alanını src_lang'dan tüm diğer dil kayıtlarına kopyalar.
    Body (form): field=hero_image_url&src_lang=tr
    Yanıt: {"ok": true, "synced_to": ["en","de",...], "value": "/static/..."}
    """
    if not admin:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    form     = await request.form()
    field    = (form.get("field") or "").strip()
    src_lang = (form.get("src_lang") or "tr").strip()

    allowed = set(SHARED_IMAGE_FIELDS) | {f"svc{i}_image" for i in range(1, 5)}
    if field not in allowed:
        return JSONResponse({"error": "Geçersiz alan"}, status_code=400)

    src_hp = db.query(HomepageContent).filter(HomepageContent.lang == src_lang).first()
    if not src_hp:
        return JSONResponse({"error": "Kaynak dil kaydı bulunamadı"}, status_code=404)

    src_data = src_hp.get_data() or {}

    # Değeri bul (svc görsel → liste içinden)
    if field.startswith("svc") and field.endswith("_image"):
        try:
            idx = int(field[3]) - 1  # "svc2_image" → 1
        except (ValueError, IndexError):
            return JSONResponse({"error": "Geçersiz svc alanı"}, status_code=400)
        svcs = src_data.get("services", [])
        image_value = svcs[idx].get("image", "") if idx < len(svcs) else ""
    else:
        image_value = src_data.get(field, "")

    if not image_value:
        return JSONResponse({"error": "Kaynak görsel boş"}, status_code=404)

    # Tüm diğer dillere yaz
    updated = []
    for lng in SUPPORTED_LANGS:
        if lng == src_lang:
            continue
        dest = db.query(HomepageContent).filter(HomepageContent.lang == lng).first()
        if not dest:
            dest = HomepageContent(lang=lng, data="{}")
            db.add(dest)
            db.flush()
        dest_data = dest.get_data() or {}

        if field.startswith("svc") and field.endswith("_image"):
            svcs = dest_data.get("services", [])
            while len(svcs) <= idx:
                svcs.append({})
            svcs[idx]["image"] = image_value
            dest_data["services"] = svcs
        else:
            dest_data[field] = image_value

        dest.set_data(dest_data)
        updated.append(lng)

    db.commit()
    return JSONResponse({"ok": True, "synced_to": updated, "value": image_value})


@router.post("/esk/homepage/save")
async def admin_homepage_save(
    request: Request,
    db: Session = Depends(get_db),
    admin: str = Depends(admin_required),
):
    if not admin:
        return RedirectResponse("/esk/login", status_code=302)
    try:
        form   = await request.form()
        lang   = form.get("lang", "tr")
        tab    = form.get("tab", "hero")
        hp     = db.query(HomepageContent).filter(HomepageContent.lang == lang).first()
        if not hp:
            hp = HomepageContent(lang=lang, data="{}")
            db.add(hp)
            db.flush()
        existing = hp.get_data() or {}

        def _f(key, default=""):
            return form.get(key, existing.get(key, default))

        # Hero
        if tab == "hero":
            existing.update({
                "hero_title":     _f("hero_title"),
                "hero_subtitle":  _f("hero_subtitle"),
                "hero_btn1_text": _f("hero_btn1_text"),
                "hero_btn1_url":  _f("hero_btn1_url"),
                "hero_btn2_text": _f("hero_btn2_text"),
                "hero_btn2_url":  _f("hero_btn2_url"),
                "hero_image_url": _f("hero_image_url"),
            })

        # Stats
        elif tab == "stats":
            stats = []
            for i in range(1, 5):
                stats.append({
                    "icon":  form.get(f"stat{i}_icon",  ""),
                    "value": form.get(f"stat{i}_value", ""),
                    "label": form.get(f"stat{i}_label", ""),
                })
            existing["stats"] = stats

        # Services
        elif tab == "services":
            existing["services_title"] = _f("services_title")
            existing["services_subtitle"] = _f("services_subtitle")
            svcs = []
            for i in range(1, 5):
                svcs.append({
                    "title": form.get(f"svc{i}_title", ""),
                    "image": form.get(f"svc{i}_image", ""),
                    "url":   form.get(f"svc{i}_url",   ""),
                    "short_description": form.get(f"svc{i}_short_description", ""),
                })
            existing["services"] = svcs

        # Raw Materials (Global Raw Material Trading)
        elif tab == "raw_materials":
            existing["raw_materials_title"] = _f("raw_materials_title")
            existing["raw_materials_p1"] = _f("raw_materials_p1")
            existing["raw_materials_p2"] = _f("raw_materials_p2")
            existing["raw_materials_btn_text"] = _f("raw_materials_btn_text")
            existing["raw_materials_btn_url"] = _f("raw_materials_btn_url")
            existing["raw_materials_image_url"] = _f("raw_materials_image_url")

        # Private Label (We Manufacture for Global Brands)
        elif tab == "private_label":
            existing["private_label_title"] = _f("private_label_title")
            existing["private_label_text"] = _f("private_label_text")
            existing["private_label_image_url"] = _f("private_label_image_url")
            pl_cards = []
            for i in range(1, 5):
                pl_cards.append({
                    "title": form.get(f"pl{i}_title", ""),
                    "description": form.get(f"pl{i}_description", ""),
                })
            existing["private_label_cards"] = pl_cards

        # Export (Exporting to 70+ Countries)
        elif tab == "export":
            existing["export_title"] = _f("export_title")
            existing["export_subtitle"] = _f("export_subtitle")
            export_stats = []
            for i in range(1, 4):
                export_stats.append({
                    "value": form.get(f"export_stat{i}_value", ""),
                    "label": form.get(f"export_stat{i}_label", ""),
                })
            existing["export_stats"] = export_stats

        # Certification (Certification & Regulatory Support)
        elif tab == "certification":
            existing["cert_title"] = _f("cert_title")
            existing["cert_subtitle"] = _f("cert_subtitle")
            cert_cards = []
            for i in range(1, 5):
                cert_cards.append({
                    "title": form.get(f"cert{i}_title", ""),
                    "description": form.get(f"cert{i}_description", ""),
                    "icon": form.get(f"cert{i}_icon", "✓"),
                })
            existing["cert_cards"] = cert_cards

        # Products band
        elif tab == "products":
            existing["products_title"] = _f("products_title")
            bullets = []
            for i in range(1, 5):
                bullets.append({
                    "bold": form.get(f"bullet{i}_bold", ""),
                    "text": form.get(f"bullet{i}_text", ""),
                })
            existing["product_bullets"] = bullets

        # Nav & Footer links
        elif tab == "nav":
            existing["logo_sub"] = _f("logo_sub")
            existing["nav_cta_text"] = _f("nav_cta_text")
            existing["nav_cta_url"]  = _f("nav_cta_url")
            nav_links = []
            for i in range(1, 7):
                lbl = form.get(f"nav{i}_label", "")
                url = form.get(f"nav{i}_url",   "")
                if lbl:
                    nav_links.append({"label": lbl, "url": url})
            existing["nav_links"] = nav_links

        # CTA / Partners
        elif tab == "cta":
            existing["cta_title"]    = _f("cta_title")
            cta_sub = _f("cta_subtitle") or _f("sticky_sub")
            existing["cta_subtitle"] = cta_sub
            existing["sticky_sub"]   = cta_sub
            existing["cta_btn_text"] = _f("cta_btn_text")
            existing["cta_btn_url"]  = _f("cta_btn_url")
            existing["partners"]     = _f("partners")
            existing["sticky_title"] = _f("sticky_title")
            badges_raw = form.get("cta_badges", existing.get("cta_badges", "ISO,GMP,REACH"))
            existing["cta_badges"] = badges_raw

        # SEO
        elif tab == "seo":
            existing["meta_title"]       = _f("meta_title")
            existing["meta_description"] = _f("meta_description")
            existing["og_title"]         = _f("og_title")
            existing["og_description"]   = _f("og_description")

        hp.set_data(existing)
        db.commit()
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        err_msg = str(e)[:150].replace('"', '').replace("'", '')
        return RedirectResponse(
            f"/esk/homepage?lang={lang}&tab={tab}&save_error={err_msg}",
            status_code=302
        )
    return RedirectResponse(f"/esk/homepage?lang={lang}&tab={tab}&saved=1", status_code=302)
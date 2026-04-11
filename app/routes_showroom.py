from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os, math, json
from datetime import date

from app.database import get_db
from app.models import Product, ProductTranslation, ProductRating, QuoteRequest, Page, PageTranslation, FaqItem
from pydantic import BaseModel
from app.config import CATEGORIES
from app.services.currency_service import get_rates, format_price, LANG_CURRENCY

router = APIRouter()

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

SUPPORTED_LANGS = ["en", "tr", "de", "fr", "ar", "ru", "es"]
DEFAULT_LANG    = "en"

# Dil adları — header dil seçicisinde gösterilir
LANG_LABELS = {
    "en": "English", "tr": "Türkçe", "de": "Deutsch", "fr": "Français",
    "ar": "العربية", "ru": "Русский", "es": "Español",
}

# ── Dile özgü URL segmentleri ─────────────────────────────
PRODUCT_SEGMENT = {
    "en": "product",
    "tr": "urun",
    "de": "produkt",
    "fr": "produit",
    "ar": "muntaj",
    "ru": "produkt",
    "es": "producto",
}

SHOWROOM_SEGMENT = {
    "en": "products",
    "tr": "urunler",
    "de": "produkte",
    "fr": "produits",
    "ar": "products",
    "ru": "produkty",
    "es": "productos",
}

# Kategori URL segmenti (dile göre)
CATEGORY_SEGMENT = {
    "en": "category",
    "tr": "kategori",
    "de": "kategorie",
    "fr": "categorie",
    "ar": "category",
    "ru": "kategoriya",
    "es": "categoria",
}

# Kategorilerin çok dilli isimleri
CATEGORY_LABELS = {
    "Cilt Bakım":          {"tr": "Cilt Bakım",          "en": "Skin Care",           "de": "Hautpflege",         "fr": "Soin de la peau",           "ar": "العناية بالبشرة",   "ru": "Уход за кожей",       "es": "Cuidado de la piel"},
    "Saç Bakım":           {"tr": "Saç Bakım",           "en": "Hair Care",            "de": "Haarpflege",         "fr": "Soin des cheveux",          "ar": "العناية بالشعر",    "ru": "Уход за волосами",    "es": "Cuidado del cabello"},
    "Kişisel Bakım":       {"tr": "Kişisel Bakım",       "en": "Personal Care",        "de": "Körperpflege",       "fr": "Soins personnels",          "ar": "العناية الشخصية",   "ru": "Личная гигиена",      "es": "Cuidado personal"},
    "Makyaj":              {"tr": "Makyaj",              "en": "Makeup",               "de": "Make-up",            "fr": "Maquillage",                "ar": "مكياج",             "ru": "Макияж",              "es": "Maquillaje"},
    "Parfüm":              {"tr": "Parfüm",              "en": "Perfume",              "de": "Parfüm",             "fr": "Parfum",                    "ar": "عطر",               "ru": "Парфюм",              "es": "Perfume"},
    "Ortam Kokuları":      {"tr": "Ortam Kokuları",      "en": "Room Fragrances",      "de": "Raumdüfte",          "fr": "Senteurs d'intérieur",      "ar": "روائح المنزل",      "ru": "Ароматы для дома",    "es": "Fragancias de ambiente"},
    "Genel Temizlik":      {"tr": "Genel Temizlik",      "en": "General Cleaning",     "de": "Allgemeinreinigung", "fr": "Nettoyage général",         "ar": "تنظيف عام",         "ru": "Общая уборка",        "es": "Limpieza general"},
    "Çamaşır Yıkama":     {"tr": "Çamaşır Yıkama",     "en": "Laundry",              "de": "Wäsche",             "fr": "Lessive",                   "ar": "غسيل الملابس",      "ru": "Стирка",              "es": "Lavandería"},
    "Bulaşık Yıkama":     {"tr": "Bulaşık Yıkama",     "en": "Dishwashing",          "de": "Geschirrspülen",     "fr": "Vaisselle",                 "ar": "غسيل الأطباق",      "ru": "Мытьё посуды",        "es": "Lavavajillas"},
    "Temizlik Malzemeleri":{"tr": "Temizlik Malzemeleri","en": "Cleaning Supplies",    "de": "Reinigungsmittel",   "fr": "Produits ménagers",         "ar": "مستلزمات التنظيف",  "ru": "Чистящие средства",   "es": "Productos de limpieza"},
    "Ambalaj":             {"tr": "Ambalaj",             "en": "Packaging",            "de": "Verpackung",         "fr": "Emballage",                 "ar": "تغليف",             "ru": "Упаковка",            "es": "Embalaje"},
    "Kozmetik Hammadde":   {"tr": "Kozmetik Hammadde",   "en": "Cosmetic Raw Material","de": "Kosmetik-Rohstoffe", "fr": "Matière première cosmétique","ar": "مواد خام تجميلية", "ru": "Косметическое сырьё", "es": "Materia prima cosmética"},
    "Temizlik Hammadde":   {"tr": "Temizlik Hammadde",   "en": "Cleaning Raw Material","de": "Reinigungs-Rohstoffe","fr": "Matière première ménagère", "ar": "مواد خام للتنظيف",  "ru": "Сырьё для уборки",    "es": "Materia prima de limpieza"},
}

# ── Kategori URL Slug'ları (dile göre) ──────────────────────
CATEGORY_SLUGS_BY_LANG: dict = {
    "tr": {
        "Cilt Bakım":           "cilt-bakim",
        "Saç Bakım":            "sac-bakim",
        "Kişisel Bakım":        "kisisel-bakim",
        "Makyaj":               "makyaj",
        "Parfüm":               "parfum",
        "Ortam Kokuları":       "ortam-kokusu",
        "Genel Temizlik":       "genel-temizlik",
        "Çamaşır Yıkama":      "camasir-yikama",
        "Bulaşık Yıkama":      "bulasik-yikama",
        "Temizlik Malzemeleri": "temizlik-malzemeleri",
        "Ambalaj":              "ambalaj",
        "Kozmetik Hammadde":    "kozmetik-hammadde",
        "Temizlik Hammadde":    "temizlik-hammadde",
    },
    "en": {
        "Cilt Bakım":           "skin-care",
        "Saç Bakım":            "hair-care",
        "Kişisel Bakım":        "personal-care",
        "Makyaj":               "makeup",
        "Parfüm":               "perfume",
        "Ortam Kokuları":       "room-fragrances",
        "Genel Temizlik":       "general-cleaning",
        "Çamaşır Yıkama":      "laundry",
        "Bulaşık Yıkama":      "dishwashing",
        "Temizlik Malzemeleri": "cleaning-supplies",
        "Ambalaj":              "packaging",
        "Kozmetik Hammadde":    "cosmetic-raw-material",
        "Temizlik Hammadde":    "cleaning-raw-material",
    },
    "de": {
        "Cilt Bakım":           "hautpflege",
        "Saç Bakım":            "haarpflege",
        "Kişisel Bakım":        "koerperpflege",
        "Makyaj":               "make-up",
        "Parfüm":               "parfuem",
        "Ortam Kokuları":       "raumdufte",
        "Genel Temizlik":       "allgemeinreinigung",
        "Çamaşır Yıkama":      "waesche",
        "Bulaşık Yıkama":      "geschirrspuelen",
        "Temizlik Malzemeleri": "reinigungsmittel",
        "Ambalaj":              "verpackung",
        "Kozmetik Hammadde":    "kosmetik-rohstoffe",
        "Temizlik Hammadde":    "reinigungs-rohstoffe",
    },
    "fr": {
        "Cilt Bakım":           "soin-de-la-peau",
        "Saç Bakım":            "soin-des-cheveux",
        "Kişisel Bakım":        "soins-personnels",
        "Makyaj":               "maquillage",
        "Parfüm":               "parfum",
        "Ortam Kokuları":       "senteurs-interieur",
        "Genel Temizlik":       "nettoyage-general",
        "Çamaşır Yıkama":      "lessive",
        "Bulaşık Yıkama":      "vaisselle",
        "Temizlik Malzemeleri": "produits-menagers",
        "Ambalaj":              "emballage",
        "Kozmetik Hammadde":    "matiere-premiere-cosmetique",
        "Temizlik Hammadde":    "matiere-premiere-menagere",
    },
    "ar": {
        "Cilt Bakım":           "skin-care",
        "Saç Bakım":            "hair-care",
        "Kişisel Bakım":        "personal-care",
        "Makyaj":               "makeup",
        "Parfüm":               "perfume",
        "Ortam Kokuları":       "room-fragrances",
        "Genel Temizlik":       "general-cleaning",
        "Çamaşır Yıkama":      "laundry",
        "Bulaşık Yıkama":      "dishwashing",
        "Temizlik Malzemeleri": "cleaning-supplies",
        "Ambalaj":              "packaging",
        "Kozmetik Hammadde":    "cosmetic-raw-material",
        "Temizlik Hammadde":    "cleaning-raw-material",
    },
    "ru": {
        "Cilt Bakım":           "uhod-za-kozhey",
        "Saç Bakım":            "uhod-za-volosami",
        "Kişisel Bakım":        "lichnaya-gigiena",
        "Makyaj":               "makiyazh",
        "Parfüm":               "parfyum",
        "Ortam Kokuları":       "aromaty-dlya-doma",
        "Genel Temizlik":       "obshchaya-uborka",
        "Çamaşır Yıkama":      "stirka",
        "Bulaşık Yıkama":      "mytye-posudy",
        "Temizlik Malzemeleri": "chistyashchie-sredstva",
        "Ambalaj":              "upakovka",
        "Kozmetik Hammadde":    "kosmeticheskoe-syre",
        "Temizlik Hammadde":    "syre-dlya-uborki",
    },
    "es": {
        "Cilt Bakım":           "cuidado-de-la-piel",
        "Saç Bakım":            "cuidado-del-cabello",
        "Kişisel Bakım":        "cuidado-personal",
        "Makyaj":               "maquillaje",
        "Parfüm":               "perfume",
        "Ortam Kokuları":       "fragancias-de-ambiente",
        "Genel Temizlik":       "limpieza-general",
        "Çamaşır Yıkama":      "lavanderia",
        "Bulaşık Yıkama":      "lavavajillas",
        "Temizlik Malzemeleri": "productos-de-limpieza",
        "Ambalaj":              "embalaje",
        "Kozmetik Hammadde":    "materia-prima-cosmetica",
        "Temizlik Hammadde":    "materia-prima-limpieza",
    },
}

# TR slugs kept as top-level dict for backward compat (seeding in main.py / routes_admin.py)
CATEGORY_SLUGS: dict = CATEGORY_SLUGS_BY_LANG["tr"]

# Ters eşleştirme: her dil için slug → Türkçe DB anahtarı
SLUG_TO_CATEGORY_BY_LANG: dict = {
    lang: {slug: key for key, slug in slugs.items()}
    for lang, slugs in CATEGORY_SLUGS_BY_LANG.items()
}
# backward compat alias (TR slugs)
SLUG_TO_CATEGORY: dict = SLUG_TO_CATEGORY_BY_LANG["tr"]


def get_category_label(category_key: str, lang: str) -> str:
    labels = CATEGORY_LABELS.get(category_key, {})
    return labels.get(lang, category_key)


def category_url(lang: str, category_key: str) -> str:
    """Kategori filtreleme URL'i — dile özgü slug kullanır."""
    seg   = CATEGORY_SEGMENT.get(lang, "category")
    slugs = CATEGORY_SLUGS_BY_LANG.get(lang, CATEGORY_SLUGS_BY_LANG["en"])
    slug  = slugs.get(category_key, category_key.lower().replace(" ", "-"))
    if lang == DEFAULT_LANG:
        return f"/{seg}/{slug}"
    return f"/{lang}/{seg}/{slug}"


BASKET_SEGMENT = {
    "en": "basket",
    "tr": "sepet",
    "de": "warenkorb",
    "fr": "panier",
    "ar": "salla",
    "ru": "korzina",
    "es": "carrito",
}

# ── UI Metinleri ──────────────────────────────────────────
UI = {
    "en": {
        "home": "Home", "products": "Products", "basket": "Basket",
        "add_to_cart": "Add to Cart", "wholesale": "Wholesale Order System",
        "hero_title": "Wholesale Product Catalog",
        "hero_sub": "Minimum order: 1 Pallet. Increases in steps of 10 boxes.",
        "in_basket": "In basket", "discount": "discount",
        "description": "Description", "logistics": "Logistics & Discount",
        "media": "Media", "documents": "Documents", "export": "Export Countries",
        "msds": "Safety Data Sheet", "tds": "Technical Data Sheet",
        "analysis": "Analysis Report", "quality": "Quality Certificate",
        "no_desc": "No description available.",
        "pieces_box": "Pcs / Box", "boxes_pallet": "Boxes / Pallet",
        "min_order": "Min. Order",
        "update": "Update", "remove": "Remove", "basket_total": "Basket Total",
        "empty_basket": "Your basket is empty.", "back_to_products": "Back to Products",
        "logistics_sim": "Logistics Simulation", "total_boxes": "Total Boxes",
        "total_pallets": "Total Pallets", "recommended": "Recommended Container",
        "remaining_20": "20FT remaining pallets", "remaining_40": "40FT remaining pallets",
        "order_request": "Create Order Request", "company": "Company Name *",
        "contact": "Contact Person *", "phone": "WhatsApp / Phone *",
        "email": "E-mail *", "notes": "Notes (optional)",
        "no_desc_long": "No description available for this product.",
        "barcode": "Barcode",
        "qty": "Qty", "boxes": "Boxes", "pallets": "Pallets", "total": "total",
        "tab_desc": "Description", "tab_logistics": "Logistics & Discount",
        "tab_media": "Media", "tab_docs": "Documents", "tab_export": "Export",
        "below_2pal": "Below 2 Pallets", "amount": "Amount",
        "unit_price": "Unit Price", "export_text": "This product is exported to:",
        "video_product": "Product Video", "video_loading": "Loading Video",
        "no_video": "Your browser does not support video.",
        "discount_active": "discount active",
        "discount_next": "more to get",
        "discount_max": "12% discount active — maximum discount reached",
        "category_label": "Category", "all_products": "All Products",
        "filter_all": "All", "sort_label": "Sort",
        "sort_default": "Default", "sort_price_asc": "Price: Low → High",
        "sort_price_desc": "Price: High → Low", "sort_rating_asc": "Rating: Low → High",
        "sort_rating_desc": "Rating: High → Low", "filter_results": "products",
        "hp_about": "About Us", "hp_services": "Production Services",
        "hp_products": "Products", "hp_export": "Export", "hp_contact": "Contact",
        "hp_get_quote": "Get a Quote",
        "hp_hero_line1": "YOUR RELIABLE", "hp_hero_line2": "PARTNER IN",
        "hp_hero_line3": "INDUSTRIAL PRODUCTION",
        "hp_hero_sub": "Cosmetics, Detergent, Perfume Manufacturing & Raw Material Supply",
        "hp_stat_years": "Years Experience", "hp_stat_years_label": "Industry expertise",
        "hp_stat_countries": "Countries", "hp_stat_countries_label": "Export markets",
        "hp_stat_cert_label": "Certifications",
        "hp_stat_fason": "Contract Mfg.", "hp_stat_fason_label": "Solutions",
        "hp_services_title": "OUR SERVICES",
        "hp_svc_cosmetic": "Cosmetics Manufacturing",
        "hp_svc_detergent": "Detergent & Cleaning Production",
        "hp_svc_parfum": "Perfume & Deodorant Production",
        "hp_svc_rawmat": "Raw Material Supply & Consulting",
        "hp_detail": "Learn More",
        "hp_products_title": "OUR PRODUCTS",
        "hp_prod_fason_bold": "Contract", "hp_prod_fason": "(Custom Manufacturing)",
        "hp_prod_quality": "High Quality Standards",
        "hp_prod_fast": "Fast & Flexible Production",
        "hp_prod_global": "Global Logistics Network",
        "hp_all_products": "Browse All Products",
        "hp_cta_title": "Get a quote for your custom production needs!",
        "hp_sticky_title": "Contact Us",
        "hp_sticky_sub": "Get a quote for your custom production solutions!",
        "footer_contact": "Contact",
        "success_eyebrow": "Quote Request",
        "success_title": "Your Request Has Been Received!",
        "success_body": "Your message has been forwarded to our team. Our average response time is 2–4 hours. We will get back to you at",
        "success_redirecting": "You will be redirected to the homepage in",
        "success_seconds": "seconds",
        "success_go_home": "Go to Homepage",
        "success_req_no": "Request No",
        "success_total": "Total Amount",
        "success_back_products": "Back to Products",
        "lp_form_title": "Get a Free Quote",
        "lp_email":    "Email", "lp_phone": "Phone", "lp_address": "Address",
        "lp_company":  "Company Name", "lp_contact": "Contact Person",
        "lp_email_ph": "Email Address", "lp_message": "Your message…",
        "lp_submit":   "Request a Quote →",
        "lp_sent":     "✓ Your request has been received. We will contact you as soon as possible.",
    },
    "tr": {
        "home": "Anasayfa", "products": "Ürünler", "basket": "Sepetim",
        "add_to_cart": "Sepete Ekle", "wholesale": "Toptan Sipariş Yönetim Sistemi",
        "hero_title": "Toptan Ürün Listesi",
        "hero_sub": "Minimum sipariş: 1 Palet. Artışlar 10 koli şeklindedir.",
        "in_basket": "Sepette", "discount": "indirim",
        "description": "Ürün Açıklaması", "logistics": "Lojistik & İndirim",
        "media": "Medya", "documents": "Belgeler", "export": "İhracat Ülkeleri",
        "msds": "Güvenlik Bilgi Formu", "tds": "Teknik Veri Sayfası",
        "analysis": "Analiz Raporu", "quality": "Kalite Belgesi",
        "no_desc": "Bu ürün için açıklama bulunmuyor.",
        "pieces_box": "Adet / Koli", "boxes_pallet": "Koli / Palet",
        "min_order": "Min. Sipariş",
        "update": "↻ Güncelle", "remove": "× Sil", "basket_total": "Sepet Toplamı",
        "empty_basket": "Sepetiniz boş.", "back_to_products": "Ürünlere Dön",
        "logistics_sim": "Lojistik Simülasyonu", "total_boxes": "Toplam Koli",
        "total_pallets": "Toplam Palet", "recommended": "Önerilen Konteyner",
        "remaining_20": "20FT kalan palet", "remaining_40": "40FT kalan palet",
        "order_request": "Sipariş Talebi Oluştur", "company": "Firma Adı *",
        "contact": "İletişim Kişisi *", "phone": "WhatsApp / Telefon *",
        "email": "E-posta *", "notes": "Not (isteğe bağlı)",
        "no_desc_long": "Bu ürün için açıklama bulunmuyor.",
        "barcode": "Barkod",
        "qty": "Adet", "boxes": "Koli", "pallets": "Palet", "total": "toplam",
        "tab_desc": "Ürün Açıklaması", "tab_logistics": "Lojistik & İndirim",
        "tab_media": "Medya", "tab_docs": "Belgeler", "tab_export": "İhracat",
        "below_2pal": "2 Palet altı", "amount": "Miktar",
        "unit_price": "Birim Fiyat", "export_text": "Bu ürün aşağıdaki ülkelere ihraç edilmektedir:",
        "video_product": "Ürün Videosu", "video_loading": "Yükleme Videosu",
        "no_video": "Tarayıcınız video oynatmayı desteklemiyor.",
        "discount_active": "indirim aktif",
        "discount_next": "adet daha ekleyin",
        "discount_max": "%12 indirim aktif — maksimum indirime ulaştınız",
        "category_label": "Kategori", "all_products": "Tüm Ürünler",
        "filter_all": "Tümü", "sort_label": "Sırala",
        "sort_default": "Varsayılan", "sort_price_asc": "Fiyat: Düşükten Yükseğe",
        "sort_price_desc": "Fiyat: Yüksekten Düşüğe", "sort_rating_asc": "Puan: Düşükten Yükseğe",
        "sort_rating_desc": "Puan: Yüksekten Düşüğe", "filter_results": "ürün",
        "hp_about": "Hakkımızda", "hp_services": "Üretim Hizmetleri",
        "hp_products": "Ürünler", "hp_export": "İhracat", "hp_contact": "İletişim",
        "hp_get_quote": "Teklif Alın",
        "hp_hero_line1": "ENDÜSTRİYEL", "hp_hero_line2": "ÜRETİMDE",
        "hp_hero_line3": "GÜVENİLİR ORTAĞINIZ",
        "hp_hero_sub": "Kozmetic, Deterjan, Parfüm Üretimi & Hammadde Tedariki",
        "hp_stat_years": "Yıllık Deneyim", "hp_stat_years_label": "Sektördeki tecrübe",
        "hp_stat_countries": "Fazla Ülke", "hp_stat_countries_label": "İhracat yapılan pazarlar",
        "hp_stat_cert_label": "Sertifikalar",
        "hp_stat_fason": "Fason Üretim", "hp_stat_fason_label": "Çözümleri",
        "hp_services_title": "HİZMETLERİMİZ",
        "hp_svc_cosmetic": "Kozmetik Üretimi",
        "hp_svc_detergent": "Deterjan & Temizlik Üretimi",
        "hp_svc_parfum": "Parfüm & Deodorant Üretimi",
        "hp_svc_rawmat": "Hammadde Tedarik & Danışmanlık",
        "hp_detail": "Detaylı Bilgi",
        "hp_products_title": "ÜRÜNLERİMİZ",
        "hp_prod_fason_bold": "Fason", "hp_prod_fason": "(Özel Üretim)",
        "hp_prod_quality": "Yüksek Kalite Standartları",
        "hp_prod_fast": "Hızlı ve Esnek Üretim",
        "hp_prod_global": "Global Lojistik Ağı",
        "hp_all_products": "Tüm Ürünleri İnceleyin",
        "hp_cta_title": "Özel üretim çözümleriniz için hemen teklif alın!",
        "hp_sticky_title": "Bizimle İletişime Geçin",
        "hp_sticky_sub": "Özel Üretim çözümleriniz için hemen teklif alın!",
        "footer_contact": "İletişim",
        "success_eyebrow": "Teklif Talebi",
        "success_title": "Talebiniz Alındı!",
        "success_body": "Mesajınız ekibimize iletildi. Ortalama geri dönüş süremiz 2–4 saattir. En kısa sürede şu adrese dönüş yapacağız:",
        "success_redirecting": "Anasayfaya yönlendiriliyorsunuz…",
        "success_seconds": "saniye",
        "success_go_home": "Anasayfaya Dön",
        "success_req_no": "Talep No",
        "success_total": "Toplam Tutar",
        "success_back_products": "Ürünlere Dön",
        "lp_form_title": "Ücretsiz Teklif Alın",
        "lp_email":    "E-posta", "lp_phone": "Telefon", "lp_address": "Adres",
        "lp_company":  "Şirket Adı", "lp_contact": "İletişim Kişisi",
        "lp_email_ph": "E-posta Adresi", "lp_message": "Mesajınız…",
        "lp_submit":   "Teklif İste →",
        "lp_sent":     "✓ Talebiniz alındı. En kısa sürede sizinle iletişime geçeceğiz.",
    },
    "de": {
        "home": "Startseite", "products": "Produkte", "basket": "Warenkorb",
        "add_to_cart": "In den Warenkorb", "wholesale": "Großhandel Bestellsystem",
        "hero_title": "Großhandel Produktkatalog",
        "hero_sub": "Mindestbestellung: 1 Palette. Erhöhungen in 10-Karton-Schritten.",
        "in_basket": "Im Warenkorb", "discount": "Rabatt",
        "description": "Produktbeschreibung", "logistics": "Logistik & Rabatt",
        "media": "Medien", "documents": "Dokumente", "export": "Exportländer",
        "msds": "Sicherheitsdatenblatt", "tds": "Technisches Datenblatt",
        "analysis": "Analysebericht", "quality": "Qualitätszertifikat",
        "no_desc": "Keine Beschreibung verfügbar.",
        "pieces_box": "Stk / Karton", "boxes_pallet": "Karton / Palette",
        "min_order": "Mindestbestellung",
        "update": "↻ Aktualisieren", "remove": "× Entfernen", "basket_total": "Warenkorbsumme",
        "empty_basket": "Ihr Warenkorb ist leer.", "back_to_products": "Zurück zu Produkten",
        "logistics_sim": "Logistik-Simulation", "total_boxes": "Gesamt Kartons",
        "total_pallets": "Gesamt Paletten", "recommended": "Empfohlener Container",
        "remaining_20": "20FT verbleibende Paletten", "remaining_40": "40FT verbleibende Paletten",
        "order_request": "Bestellanfrage erstellen", "company": "Firmenname *",
        "contact": "Kontaktperson *", "phone": "WhatsApp / Telefon *",
        "email": "E-Mail *", "notes": "Anmerkungen (optional)",
        "no_desc_long": "Für dieses Produkt ist keine Beschreibung verfügbar.",
        "barcode": "Barcode",
        "qty": "Stk", "boxes": "Kartons", "pallets": "Paletten", "total": "gesamt",
        "tab_desc": "Produktbeschreibung", "tab_logistics": "Logistik & Rabatt",
        "tab_media": "Medien", "tab_docs": "Dokumente", "tab_export": "Export",
        "below_2pal": "Unter 2 Paletten", "amount": "Menge",
        "unit_price": "Stückpreis", "export_text": "Dieses Produkt wird in folgende Länder exportiert:",
        "video_product": "Produktvideo", "video_loading": "Ladevideo",
        "no_video": "Ihr Browser unterstützt kein Video.",
        "discount_active": "Rabatt aktiv",
        "discount_next": "mehr hinzufügen für",
        "discount_max": "12% Rabatt aktiv — maximaler Rabatt erreicht",
        "category_label": "Kategorie", "all_products": "Alle Produkte",
        "filter_all": "Alle", "sort_label": "Sortieren",
        "sort_default": "Standard", "sort_price_asc": "Preis: Aufsteigend",
        "sort_price_desc": "Preis: Absteigend", "sort_rating_asc": "Bewertung: Aufsteigend",
        "sort_rating_desc": "Bewertung: Absteigend", "filter_results": "Produkte",
        "hp_about": "Über uns", "hp_services": "Produktionsdienstleistungen",
        "hp_products": "Produkte", "hp_export": "Export", "hp_contact": "Kontakt",
        "hp_get_quote": "Angebot anfragen",
        "hp_hero_line1": "IHR ZUVERLÄSSIGER", "hp_hero_line2": "PARTNER IN DER",
        "hp_hero_line3": "INDUSTRIELLEN PRODUKTION",
        "hp_hero_sub": "Kosmetik, Waschmittel, Parfüm-Herstellung & Rohstoffversorgung",
        "hp_stat_years": "Jahre Erfahrung", "hp_stat_years_label": "Branchenkompetenz",
        "hp_stat_countries": "Länder", "hp_stat_countries_label": "Exportmärkte",
        "hp_stat_cert_label": "Zertifikate",
        "hp_stat_fason": "Lohnfertigung", "hp_stat_fason_label": "Lösungen",
        "hp_services_title": "UNSERE LEISTUNGEN",
        "hp_svc_cosmetic": "Kosmetikherstellung",
        "hp_svc_detergent": "Waschmittel & Reinigungsproduktion",
        "hp_svc_parfum": "Parfüm & Deodorant-Produktion",
        "hp_svc_rawmat": "Rohstoffversorgung & Beratung",
        "hp_detail": "Mehr erfahren",
        "hp_products_title": "UNSERE PRODUKTE",
        "hp_prod_fason_bold": "Lohnfertigung", "hp_prod_fason": "(individuelle Herstellung)",
        "hp_prod_quality": "Hohe Qualitätsstandards",
        "hp_prod_fast": "Schnelle & flexible Produktion",
        "hp_prod_global": "Globales Logistiknetz",
        "hp_all_products": "Alle Produkte ansehen",
        "hp_cta_title": "Holen Sie sich ein Angebot für Ihre individuelle Produktion!",
        "hp_sticky_title": "Kontaktieren Sie uns",
        "hp_sticky_sub": "Fordern Sie jetzt Ihr Angebot an!",
        "footer_contact": "Kontakt",
        "success_eyebrow": "Angebotsanfrage",
        "success_title": "Ihre Anfrage wurde erhalten!",
        "success_body": "Ihre Nachricht wurde an unser Team weitergeleitet. Unsere durchschnittliche Antwortzeit beträgt 2–4 Stunden. Wir melden uns unter:",
        "success_redirecting": "Sie werden zur Startseite weitergeleitet…",
        "success_seconds": "Sekunden",
        "success_go_home": "Zur Startseite",
        "success_req_no": "Anfrage-Nr.",
        "success_total": "Gesamtbetrag",
        "success_back_products": "Zurück zu Produkten",
        "lp_form_title": "Kostenloses Angebot erhalten",
        "lp_email":    "E-Mail", "lp_phone": "Telefon", "lp_address": "Adresse",
        "lp_company":  "Firmenname", "lp_contact": "Kontaktperson",
        "lp_email_ph": "E-Mail-Adresse", "lp_message": "Ihre Nachricht…",
        "lp_submit":   "Angebot anfragen →",
        "lp_sent":     "✓ Ihre Anfrage wurde erhalten. Wir werden uns so bald wie möglich bei Ihnen melden.",
    },
    "fr": {
        "home": "Accueil", "products": "Produits", "basket": "Panier",
        "add_to_cart": "Ajouter au panier", "wholesale": "Système de commande en gros",
        "hero_title": "Catalogue de produits en gros",
        "hero_sub": "Commande minimum: 1 palette. Augmentations par tranches de 10 cartons.",
        "in_basket": "Dans le panier", "discount": "remise",
        "description": "Description du produit", "logistics": "Logistique & Remise",
        "media": "Médias", "documents": "Documents", "export": "Pays d'exportation",
        "msds": "Fiche de données de sécurité", "tds": "Fiche technique",
        "analysis": "Rapport d'analyse", "quality": "Certificat de qualité",
        "no_desc": "Aucune description disponible.",
        "pieces_box": "Pcs / Carton", "boxes_pallet": "Cartons / Palette",
        "min_order": "Commande min.",
        "update": "↻ Mettre à jour", "remove": "× Supprimer", "basket_total": "Total du panier",
        "empty_basket": "Votre panier est vide.", "back_to_products": "Retour aux produits",
        "logistics_sim": "Simulation logistique", "total_boxes": "Total cartons",
        "total_pallets": "Total palettes", "recommended": "Conteneur recommandé",
        "remaining_20": "Palettes restantes 20FT", "remaining_40": "Palettes restantes 40FT",
        "order_request": "Créer une demande de commande", "company": "Nom de l'entreprise *",
        "contact": "Personne de contact *", "phone": "WhatsApp / Téléphone *",
        "email": "E-mail *", "notes": "Notes (optionnel)",
        "no_desc_long": "Aucune description disponible pour ce produit.",
        "barcode": "Code-barres",
        "qty": "Qté", "boxes": "Cartons", "pallets": "Palettes", "total": "total",
        "tab_desc": "Description du produit", "tab_logistics": "Logistique & Remise",
        "tab_media": "Médias", "tab_docs": "Documents", "tab_export": "Export",
        "below_2pal": "Moins de 2 palettes", "amount": "Quantité",
        "unit_price": "Prix unitaire", "export_text": "Ce produit est exporté vers:",
        "video_product": "Vidéo produit", "video_loading": "Vidéo de chargement",
        "no_video": "Votre navigateur ne supporte pas la vidéo.",
        "discount_active": "remise active",
        "discount_next": "de plus pour",
        "discount_max": "Remise 12% active — remise maximale atteinte",
        "category_label": "Catégorie", "all_products": "Tous les produits",
        "filter_all": "Tout", "sort_label": "Trier",
        "sort_default": "Défaut", "sort_price_asc": "Prix: Croissant",
        "sort_price_desc": "Prix: Décroissant", "sort_rating_asc": "Note: Croissante",
        "sort_rating_desc": "Note: Décroissante", "filter_results": "produits",
        "hp_about": "À propos", "hp_services": "Services de production",
        "hp_products": "Produits", "hp_export": "Export", "hp_contact": "Contact",
        "hp_get_quote": "Demander un devis",
        "hp_hero_line1": "VOTRE PARTENAIRE", "hp_hero_line2": "FIABLE EN",
        "hp_hero_line3": "PRODUCTION INDUSTRIELLE",
        "hp_hero_sub": "Fabrication de cosmétiques, détergents, parfums & fourniture de matières premières",
        "hp_stat_years": "Ans d'expérience", "hp_stat_years_label": "Expertise sectorielle",
        "hp_stat_countries": "Pays", "hp_stat_countries_label": "Marchés d'exportation",
        "hp_stat_cert_label": "Certifications",
        "hp_stat_fason": "Fabrication sous contrat", "hp_stat_fason_label": "Solutions",
        "hp_services_title": "NOS SERVICES",
        "hp_svc_cosmetic": "Fabrication de cosmétiques",
        "hp_svc_detergent": "Production de détergents & nettoyants",
        "hp_svc_parfum": "Production de parfums & déodorants",
        "hp_svc_rawmat": "Fourniture de matières premières & conseil",
        "hp_detail": "En savoir plus",
        "hp_products_title": "NOS PRODUITS",
        "hp_prod_fason_bold": "Sous-traitance", "hp_prod_fason": "(fabrication personnalisée)",
        "hp_prod_quality": "Standards de haute qualité",
        "hp_prod_fast": "Production rapide & flexible",
        "hp_prod_global": "Réseau logistique mondial",
        "hp_all_products": "Voir tous les produits",
        "hp_cta_title": "Obtenez un devis pour vos besoins de production personnalisés !",
        "hp_sticky_title": "Contactez-nous",
        "hp_sticky_sub": "Obtenez un devis pour vos solutions de production personnalisées !",
        "footer_contact": "Contact",
        "success_eyebrow": "Demande de devis",
        "success_title": "Votre demande a été reçue !",
        "success_body": "Votre message a été transmis à notre équipe. Notre délai de réponse moyen est de 2 à 4 heures. Nous vous répondrons à :",
        "success_redirecting": "Vous allez être redirigé vers la page d'accueil…",
        "success_seconds": "secondes",
        "success_go_home": "Retour à l'accueil",
        "success_req_no": "N° de demande",
        "success_total": "Montant total",
        "success_back_products": "Retour aux produits",
        "lp_form_title": "Obtenir un devis gratuit",
        "lp_email":    "E-mail", "lp_phone": "Téléphone", "lp_address": "Adresse",
        "lp_company":  "Nom de l'entreprise", "lp_contact": "Personne de contact",
        "lp_email_ph": "Adresse e-mail", "lp_message": "Votre message…",
        "lp_submit":   "Demander un devis →",
        "lp_sent":     "✓ Votre demande a été reçue. Nous vous contacterons dans les plus brefs délais.",
    },
    "ar": {
        "home": "الرئيسية", "products": "المنتجات", "basket": "السلة",
        "add_to_cart": "أضف إلى السلة", "wholesale": "نظام طلب الجملة",
        "hero_title": "كتالوج منتجات الجملة",
        "hero_sub": "الحد الأدنى للطلب: 1 بالت. زيادات بخطوات 10 صناديق.",
        "in_basket": "في السلة", "discount": "خصم",
        "description": "وصف المنتج", "logistics": "اللوجستيات والخصم",
        "media": "وسائط", "documents": "مستندات", "export": "دول التصدير",
        "msds": "صحيفة بيانات السلامة", "tds": "الورقة الفنية",
        "analysis": "تقرير التحليل", "quality": "شهادة الجودة",
        "no_desc": "لا يوجد وصف متاح.",
        "pieces_box": "قطعة / صندوق", "boxes_pallet": "صندوق / بالت",
        "min_order": "الحد الأدنى للطلب",
        "update": "↻ تحديث", "remove": "× حذف", "basket_total": "إجمالي السلة",
        "empty_basket": "سلتك فارغة.", "back_to_products": "العودة إلى المنتجات",
        "logistics_sim": "محاكاة اللوجستيات", "total_boxes": "إجمالي الصناديق",
        "total_pallets": "إجمالي البالتات", "recommended": "الحاوية الموصى بها",
        "remaining_20": "بالتات متبقية 20FT", "remaining_40": "بالتات متبقية 40FT",
        "order_request": "إنشاء طلب شراء", "company": "اسم الشركة *",
        "contact": "جهة الاتصال *", "phone": "واتساب / هاتف *",
        "email": "البريد الإلكتروني *", "notes": "ملاحظات (اختياري)",
        "no_desc_long": "لا يوجد وصف متاح لهذا المنتج.",
        "barcode": "باركود",
        "qty": "كمية", "boxes": "صناديق", "pallets": "بالتات", "total": "إجمالي",
        "tab_desc": "وصف المنتج", "tab_logistics": "اللوجستيات والخصم",
        "tab_media": "وسائط", "tab_docs": "مستندات", "tab_export": "تصدير",
        "below_2pal": "أقل من 2 بالت", "amount": "الكمية",
        "unit_price": "سعر الوحدة", "export_text": "يُصدَّر هذا المنتج إلى:",
        "video_product": "فيديو المنتج", "video_loading": "جارٍ التحميل",
        "no_video": "متصفحك لا يدعم الفيديو.",
        "discount_active": "خصم مفعّل",
        "discount_next": "أضف المزيد للحصول على",
        "discount_max": "خصم 12% مفعّل — تم الوصول إلى أقصى خصم",
        "category_label": "الفئة", "all_products": "جميع المنتجات",
        "filter_all": "الكل", "sort_label": "ترتيب",
        "sort_default": "افتراضي", "sort_price_asc": "السعر: تصاعدي",
        "sort_price_desc": "السعر: تنازلي", "sort_rating_asc": "التقييم: تصاعدي",
        "sort_rating_desc": "التقييم: تنازلي", "filter_results": "منتجات",
        "hp_about": "من نحن", "hp_services": "خدمات الإنتاج",
        "hp_products": "المنتجات", "hp_export": "التصدير", "hp_contact": "اتصل بنا",
        "hp_get_quote": "احصل على عرض سعر",
        "hp_hero_line1": "شريككم الموثوق", "hp_hero_line2": "في الإنتاج",
        "hp_hero_line3": "الصناعي",
        "hp_hero_sub": "تصنيع مستحضرات التجميل والمنظفات والعطور وتوريد المواد الخام",
        "hp_stat_years": "سنة خبرة", "hp_stat_years_label": "خبرة في القطاع",
        "hp_stat_countries": "دولة", "hp_stat_countries_label": "أسواق التصدير",
        "hp_stat_cert_label": "شهادات",
        "hp_stat_fason": "تصنيع تعاقدي", "hp_stat_fason_label": "حلول",
        "hp_services_title": "خدماتنا",
        "hp_svc_cosmetic": "تصنيع مستحضرات التجميل",
        "hp_svc_detergent": "إنتاج المنظفات ومنتجات التنظيف",
        "hp_svc_parfum": "إنتاج العطور ومزيلات العرق",
        "hp_svc_rawmat": "توريد المواد الخام والاستشارات",
        "hp_detail": "تفاصيل",
        "hp_products_title": "منتجاتنا",
        "hp_prod_fason_bold": "تعاقدي", "hp_prod_fason": "(تصنيع مخصص)",
        "hp_prod_quality": "معايير جودة عالية",
        "hp_prod_fast": "إنتاج سريع ومرن",
        "hp_prod_global": "شبكة لوجستية عالمية",
        "hp_all_products": "تصفح جميع المنتجات",
        "hp_cta_title": "احصل على عرض سعر لاحتياجات إنتاجك المخصصة!",
        "hp_sticky_title": "تواصل معنا",
        "hp_sticky_sub": "احصل على عرض سعر لحلول الإنتاج المخصصة!",
        "footer_contact": "اتصل بنا",
        "success_eyebrow": "طلب عرض سعر",
        "success_title": "تم استلام طلبك!",
        "success_body": "تم إرسال رسالتك إلى فريقنا. متوسط وقت الاستجابة لدينا 2–4 ساعات. سنتواصل معك على:",
        "success_redirecting": "سيتم توجيهك إلى الصفحة الرئيسية…",
        "success_seconds": "ثوانٍ",
        "success_go_home": "الذهاب إلى الصفحة الرئيسية",
        "success_req_no": "رقم الطلب",
        "success_total": "المبلغ الإجمالي",
        "success_back_products": "العودة إلى المنتجات",
        "lp_form_title": "احصل على عرض سعر مجاني",
        "lp_email":    "البريد الإلكتروني", "lp_phone": "هاتف", "lp_address": "العنوان",
        "lp_company":  "اسم الشركة", "lp_contact": "جهة الاتصال",
        "lp_email_ph": "عنوان البريد الإلكتروني", "lp_message": "رسالتك…",
        "lp_submit":   "طلب عرض سعر →",
        "lp_sent":     "✓ تم استلام طلبك. سنتواصل معك في أقرب وقت ممكن.",
    },
    "ru": {
        "home": "Главная", "products": "Товары", "basket": "Корзина",
        "add_to_cart": "В корзину", "wholesale": "Система оптовых заказов",
        "hero_title": "Оптовый каталог товаров",
        "hero_sub": "Минимальный заказ: 1 паллет. Увеличение шагами по 10 коробок.",
        "in_basket": "В корзине", "discount": "скидка",
        "description": "Описание товара", "logistics": "Логистика и скидки",
        "media": "Медиа", "documents": "Документы", "export": "Страны экспорта",
        "msds": "Паспорт безопасности", "tds": "Технический паспорт",
        "analysis": "Аналитический отчёт", "quality": "Сертификат качества",
        "no_desc": "Описание недоступно.",
        "pieces_box": "Шт / Коробка", "boxes_pallet": "Коробок / Паллет",
        "min_order": "Мин. заказ",
        "update": "↻ Обновить", "remove": "× Удалить", "basket_total": "Итого по корзине",
        "empty_basket": "Ваша корзина пуста.", "back_to_products": "Назад к товарам",
        "logistics_sim": "Логистический симулятор", "total_boxes": "Всего коробок",
        "total_pallets": "Всего паллет", "recommended": "Рекомендуемый контейнер",
        "remaining_20": "Остаток паллет 20FT", "remaining_40": "Остаток паллет 40FT",
        "order_request": "Создать заявку", "company": "Название компании *",
        "contact": "Контактное лицо *", "phone": "WhatsApp / Телефон *",
        "email": "E-mail *", "notes": "Примечания (необязательно)",
        "no_desc_long": "Описание для этого товара недоступно.",
        "barcode": "Штрихкод",
        "qty": "Кол-во", "boxes": "Коробки", "pallets": "Паллеты", "total": "итого",
        "tab_desc": "Описание товара", "tab_logistics": "Логистика и скидки",
        "tab_media": "Медиа", "tab_docs": "Документы", "tab_export": "Экспорт",
        "below_2pal": "Менее 2 паллет", "amount": "Количество",
        "unit_price": "Цена за единицу", "export_text": "Этот товар экспортируется в:",
        "video_product": "Видео товара", "video_loading": "Видео загрузки",
        "no_video": "Ваш браузер не поддерживает видео.",
        "discount_active": "скидка активна",
        "discount_next": "добавьте ещё для",
        "discount_max": "Скидка 12% активна — достигнута максимальная скидка",
        "category_label": "Категория", "all_products": "Все товары",
        "filter_all": "Все", "sort_label": "Сортировка",
        "sort_default": "По умолчанию", "sort_price_asc": "Цена: По возрастанию",
        "sort_price_desc": "Цена: По убыванию", "sort_rating_asc": "Рейтинг: По возрастанию",
        "sort_rating_desc": "Рейтинг: По убыванию", "filter_results": "товаров",
        "hp_about": "О нас", "hp_services": "Производственные услуги",
        "hp_products": "Товары", "hp_export": "Экспорт", "hp_contact": "Контакты",
        "hp_get_quote": "Получить предложение",
        "hp_hero_line1": "ВАШ НАДЁЖНЫЙ", "hp_hero_line2": "ПАРТНЁР В",
        "hp_hero_line3": "ПРОМЫШЛЕННОМ ПРОИЗВОДСТВЕ",
        "hp_hero_sub": "Производство косметики, моющих средств, парфюмерии и поставка сырья",
        "hp_stat_years": "Лет опыта", "hp_stat_years_label": "Отраслевая экспертиза",
        "hp_stat_countries": "Стран", "hp_stat_countries_label": "Экспортные рынки",
        "hp_stat_cert_label": "Сертификаты",
        "hp_stat_fason": "Контрактное производство", "hp_stat_fason_label": "Решения",
        "hp_services_title": "НАШИ УСЛУГИ",
        "hp_svc_cosmetic": "Производство косметики",
        "hp_svc_detergent": "Производство моющих и чистящих средств",
        "hp_svc_parfum": "Производство парфюмерии и дезодорантов",
        "hp_svc_rawmat": "Поставка сырья и консультации",
        "hp_detail": "Подробнее",
        "hp_products_title": "НАШИ ТОВАРЫ",
        "hp_prod_fason_bold": "Контрактное", "hp_prod_fason": "(индивидуальное производство)",
        "hp_prod_quality": "Высокие стандарты качества",
        "hp_prod_fast": "Быстрое и гибкое производство",
        "hp_prod_global": "Глобальная логистическая сеть",
        "hp_all_products": "Просмотреть все товары",
        "hp_cta_title": "Получите предложение для вашего индивидуального производства!",
        "hp_sticky_title": "Свяжитесь с нами",
        "hp_sticky_sub": "Получите предложение для ваших производственных решений!",
        "footer_contact": "Контакты",
        "success_eyebrow": "Запрос предложения",
        "success_title": "Ваш запрос получен!",
        "success_body": "Ваше сообщение передано нашей команде. Среднее время ответа — 2–4 часа. Мы свяжемся с вами по адресу:",
        "success_redirecting": "Вы будете перенаправлены на главную страницу…",
        "success_seconds": "секунд",
        "success_go_home": "На главную",
        "success_req_no": "№ запроса",
        "success_total": "Итоговая сумма",
        "success_back_products": "Назад к товарам",
        "lp_form_title": "Получить бесплатное предложение",
        "lp_email":    "Эл. почта", "lp_phone": "Телефон", "lp_address": "Адрес",
        "lp_company":  "Название компании", "lp_contact": "Контактное лицо",
        "lp_email_ph": "Адрес эл. почты", "lp_message": "Ваше сообщение…",
        "lp_submit":   "Запросить предложение →",
        "lp_sent":     "✓ Ваш запрос получен. Мы свяжемся с вами как можно скорее.",
    },
    "es": {
        "home": "Inicio", "products": "Productos", "basket": "Carrito",
        "add_to_cart": "Añadir al carrito", "wholesale": "Sistema de pedidos al por mayor",
        "hero_title": "Catálogo de productos al por mayor",
        "hero_sub": "Pedido mínimo: 1 palé. Incrementos en pasos de 10 cajas.",
        "in_basket": "En el carrito", "discount": "descuento",
        "description": "Descripción del producto", "logistics": "Logística y descuento",
        "media": "Medios", "documents": "Documentos", "export": "Países de exportación",
        "msds": "Ficha de datos de seguridad", "tds": "Ficha técnica",
        "analysis": "Informe de análisis", "quality": "Certificado de calidad",
        "no_desc": "No hay descripción disponible.",
        "pieces_box": "Uds / Caja", "boxes_pallet": "Cajas / Palé",
        "min_order": "Pedido mín.",
        "update": "↻ Actualizar", "remove": "× Eliminar", "basket_total": "Total del carrito",
        "empty_basket": "Tu carrito está vacío.", "back_to_products": "Volver a productos",
        "logistics_sim": "Simulación logística", "total_boxes": "Total cajas",
        "total_pallets": "Total palés", "recommended": "Contenedor recomendado",
        "remaining_20": "Palés restantes 20FT", "remaining_40": "Palés restantes 40FT",
        "order_request": "Crear solicitud de pedido", "company": "Nombre de empresa *",
        "contact": "Persona de contacto *", "phone": "WhatsApp / Teléfono *",
        "email": "Correo electrónico *", "notes": "Notas (opcional)",
        "no_desc_long": "No hay descripción disponible para este producto.",
        "barcode": "Código de barras",
        "qty": "Cant.", "boxes": "Cajas", "pallets": "Palés", "total": "total",
        "tab_desc": "Descripción del producto", "tab_logistics": "Logística y descuento",
        "tab_media": "Medios", "tab_docs": "Documentos", "tab_export": "Exportación",
        "below_2pal": "Menos de 2 palés", "amount": "Cantidad",
        "unit_price": "Precio unitario", "export_text": "Este producto se exporta a:",
        "video_product": "Vídeo del producto", "video_loading": "Vídeo de carga",
        "no_video": "Tu navegador no soporta vídeo.",
        "discount_active": "descuento activo",
        "discount_next": "añade más para",
        "discount_max": "Descuento 12% activo — descuento máximo alcanzado",
        "category_label": "Categoría", "all_products": "Todos los productos",
        "filter_all": "Todos", "sort_label": "Ordenar",
        "sort_default": "Predeterminado", "sort_price_asc": "Precio: Menor a mayor",
        "sort_price_desc": "Precio: Mayor a menor", "sort_rating_asc": "Valoración: Menor a mayor",
        "sort_rating_desc": "Valoración: Mayor a menor", "filter_results": "productos",
        "hp_about": "Sobre nosotros", "hp_services": "Servicios de producción",
        "hp_products": "Productos", "hp_export": "Exportación", "hp_contact": "Contacto",
        "hp_get_quote": "Solicitar presupuesto",
        "hp_hero_line1": "SU SOCIO DE", "hp_hero_line2": "CONFIANZA EN",
        "hp_hero_line3": "PRODUCCIÓN INDUSTRIAL",
        "hp_hero_sub": "Fabricación de cosméticos, detergentes, perfumes y suministro de materias primas",
        "hp_stat_years": "Años de experiencia", "hp_stat_years_label": "Experiencia en el sector",
        "hp_stat_countries": "Países", "hp_stat_countries_label": "Mercados de exportación",
        "hp_stat_cert_label": "Certificaciones",
        "hp_stat_fason": "Fabricación por contrato", "hp_stat_fason_label": "Soluciones",
        "hp_services_title": "NUESTROS SERVICIOS",
        "hp_svc_cosmetic": "Fabricación de cosméticos",
        "hp_svc_detergent": "Producción de detergentes y productos de limpieza",
        "hp_svc_parfum": "Producción de perfumes y desodorantes",
        "hp_svc_rawmat": "Suministro de materias primas y consultoría",
        "hp_detail": "Más información",
        "hp_products_title": "NUESTROS PRODUCTOS",
        "hp_prod_fason_bold": "Contrato", "hp_prod_fason": "(fabricación personalizada)",
        "hp_prod_quality": "Altos estándares de calidad",
        "hp_prod_fast": "Producción rápida y flexible",
        "hp_prod_global": "Red logística global",
        "hp_all_products": "Ver todos los productos",
        "hp_cta_title": "¡Solicita un presupuesto para tus necesidades de producción personalizadas!",
        "hp_sticky_title": "Contáctenos",
        "hp_sticky_sub": "¡Solicita un presupuesto para tus soluciones de producción personalizadas!",
        "footer_contact": "Contacto",
        "success_eyebrow": "Solicitud de presupuesto",
        "success_title": "¡Tu solicitud ha sido recibida!",
        "success_body": "Tu mensaje ha sido enviado a nuestro equipo. Nuestro tiempo de respuesta promedio es de 2 a 4 horas. Nos pondremos en contacto contigo en:",
        "success_redirecting": "Serás redirigido a la página de inicio…",
        "success_seconds": "segundos",
        "success_go_home": "Ir a la página de inicio",
        "success_req_no": "N.º de solicitud",
        "success_total": "Importe total",
        "success_back_products": "Volver a productos",
        "lp_form_title": "Obtener presupuesto gratuito",
        "lp_email":    "Correo electrónico", "lp_phone": "Teléfono", "lp_address": "Dirección",
        "lp_company":  "Nombre de empresa", "lp_contact": "Persona de contacto",
        "lp_email_ph": "Dirección de correo electrónico", "lp_message": "Su mensaje…",
        "lp_submit":   "Solicitar presupuesto →",
        "lp_sent":     "✓ Su solicitud ha sido recibida. Nos pondremos en contacto con usted a la brevedad.",
    },
}


# =========================================================
# URL yardımcıları
# =========================================================

def showroom_url(lang: str) -> str:
    seg = SHOWROOM_SEGMENT.get(lang, "products")
    if lang == DEFAULT_LANG:
        return f"/{seg}"
    return f"/{lang}/{seg}"


def basket_url(lang: str) -> str:
    seg = BASKET_SEGMENT.get(lang, "basket")
    if lang == DEFAULT_LANG:
        return f"/{seg}"
    return f"/{lang}/{seg}"


def product_url(lang: str, slug: str) -> str:
    seg = PRODUCT_SEGMENT.get(lang, "product")
    if lang == DEFAULT_LANG:
        return f"/{seg}/{slug}"
    return f"/{lang}/{seg}/{slug}"


def add_to_cart_url(lang: str) -> str:
    if lang == DEFAULT_LANG:
        return "/add-to-cart"
    return f"/{lang}/add-to-cart"


def update_cart_url(lang: str) -> str:
    if lang == DEFAULT_LANG:
        return "/update-cart"
    return f"/{lang}/update-cart"


def remove_cart_url(lang: str) -> str:
    if lang == DEFAULT_LANG:
        return "/remove-from-cart"
    return f"/{lang}/remove-from-cart"


def quote_url(lang: str) -> str:
    if lang == DEFAULT_LANG:
        return "/quote-request"
    return f"/{lang}/quote-request"


def home_root_url(lang: str) -> str:
    if lang == DEFAULT_LANG:
        return "/"
    return f"/{lang}"


def _get_site_settings(db, lang=None):
    """SiteSettings singleton. lang verilirse dil bazlı metinler (i18n) döner."""
    if db is None:
        fake = type("SiteSettings", (), {"id": 1, "site_name": "Heni", "get_footer_columns": lambda self: []})()
        return fake
    try:
        from app.models import SiteSettings
        s = db.query(SiteSettings).filter(SiteSettings.id == 1).first()
        if not s:
            return type("SiteSettings", (), {"id": 1, "site_name": "Heni", "get_footer_columns": lambda self: []})()
        if lang:
            return _site_for_lang(s, lang)
        return s
    except Exception:
        return type("SiteSettings", (), {"id": 1, "site_name": "Heni", "get_footer_columns": lambda self: []})()


def _site_for_lang(s, lang):
    """SiteSettings s ve lang için dil bazlı view: i18n[lang] + global alanlar."""
    i18n = s.get_i18n_data() if hasattr(s, "get_i18n_data") and callable(getattr(s, "get_i18n_data")) else {}
    data = i18n.get(lang) or i18n.get(DEFAULT_LANG) or {}
    # Fallback: legacy kolonlar (tek dil)
    def _v(key, default=""):
        return data.get(key) if data.get(key) not in (None, "") else getattr(s, key, None) or default
    footer_cols_raw = data.get("footer_columns") if "footer_columns" in data else getattr(s, "footer_columns", None)
    if isinstance(footer_cols_raw, list):
        footer_cols = footer_cols_raw
    elif footer_cols_raw:
        try:
            footer_cols = json.loads(footer_cols_raw)
        except Exception:
            footer_cols = s.get_footer_columns() if hasattr(s, "get_footer_columns") else []
    else:
        footer_cols = s.get_footer_columns() if hasattr(s, "get_footer_columns") else []

    class _SiteForLang:
        id = getattr(s, "id", 1)
        site_name = _v("site_name", "Heni")
        logo_url = getattr(s, "logo_url", None)
        logo_white_url = getattr(s, "logo_white_url", None)
        favicon_url = getattr(s, "favicon_url", None)
        contact_email = _v("contact_email")
        contact_phone = _v("contact_phone")
        contact_address = _v("contact_address")
        social_linkedin = getattr(s, "social_linkedin", None)
        social_instagram = getattr(s, "social_instagram", None)
        social_twitter = getattr(s, "social_twitter", None)
        social_whatsapp = getattr(s, "social_whatsapp", None)
        # seo_title_template ve seo_description EN i18n'inden miras alınmamalı.
        # AR/RU/ES için EN'in seo_title_template değeri miras alınırsa, template
        # {% elif site.seo_title_template %} bloğunu tetikler ve _base_title'ı ezar.
        # Yalnızca bu dilin i18n verisini kullan; yoksa DB kolonuna dön.
        _lang_only = i18n.get(lang) or {}
        seo_title_template = (
            _lang_only.get("seo_title_template")
            if _lang_only.get("seo_title_template") not in (None, "")
            else (getattr(s, "seo_title_template", None) or "")
        )
        seo_description = (
            _lang_only.get("seo_description")
            if _lang_only.get("seo_description") not in (None, "")
            else (getattr(s, "seo_description", None) or "")
        )
        analytics_code = getattr(s, "analytics_code", None)
        custom_css = getattr(s, "custom_css", None)
        footer_description = _v("footer_description")
        footer_copyright_lead = _v("footer_copyright_lead")
        footer_copyright = _v("footer_copyright")
        footer_bg_image_url = getattr(s, "footer_bg_image_url", None)
        # Sertifika logoları — footer güven bandı
        cert_logo_iso9001_url  = getattr(s, "cert_logo_iso9001_url",  None)
        cert_logo_iso14001_url = getattr(s, "cert_logo_iso14001_url", None)
        cert_logo_iso45001_url = getattr(s, "cert_logo_iso45001_url", None)
        cert_logo_gmp_url      = getattr(s, "cert_logo_gmp_url",      None)
        cert_logo_ce_url       = getattr(s, "cert_logo_ce_url",       None)
        cert_logo_fda_url      = getattr(s, "cert_logo_fda_url",      None)
        cert_logo_vegan_url    = getattr(s, "cert_logo_vegan_url",    None)
        def get_footer_columns(self):
            return footer_cols if isinstance(footer_cols, list) else []
    return _SiteForLang()


def common_ctx(request: Request, lang: str, product=None, db=None) -> dict:
    ui = UI.get(lang, UI[DEFAULT_LANG])

    if product:
        lang_urls = {l: product_url(l, product.get_slug_for(l)) for l in SUPPORTED_LANGS}
    else:
        lang_urls = {l: showroom_url(l) for l in SUPPORTED_LANGS}

    rates = get_rates()

    def price(amount_usd: float) -> str:
        return format_price(amount_usd, lang, rates)

    site = _get_site_settings(db, lang)

    # Anasayfa CMS verisi — header menü/nav için (tüm sayfalarda ortak header)
    hp_data = {}
    if db:
        try:
            from app.models import HomepageContent
            hp_row = db.query(HomepageContent).filter(HomepageContent.lang == lang).first()
            if hp_row is None:
                # Kayıt hiç yoksa EN verisine düş (ar/ru/es kaydı boşsa düşme)
                hp_en = db.query(HomepageContent).filter(HomepageContent.lang == "en").first()
                hp_data = hp_en.get_data() if hp_en else {}
            else:
                hp_data = hp_row.get_data()
        except Exception:
            pass

    return {
        "request":      request,
        "lang":         lang,
        "ui":           ui,
        "lang_urls":    lang_urls,
        "lang_labels":  LANG_LABELS,
        "cart":         request.session.get("cart", {}),
        "home_url":     home_root_url(lang),
        "showroom_url": showroom_url(lang),
        "basket_url":   basket_url(lang),
        "rates":        rates,
        "price":        price,
        "site":         site,
        "hp":           hp_data,
    }


# =========================================================
# Hesap yardımcıları
# =========================================================

def get_discount_rate(product, pallets: float) -> float:
    db_vals = [
        product.discount_5_plus_pallet, product.discount_4_pallet,
        product.discount_3_pallet, product.discount_2_pallet, product.discount_1_pallet,
    ]
    if any((v or 0) > 0 for v in db_vals):
        return product.calculate_discounted_price(pallets)
    if pallets >= 9: return 0.12
    if pallets >= 6: return 0.09
    if pallets >= 4: return 0.07
    if pallets >= 2: return 0.05
    return 0.0


def compute_basket_item(product, qty):
    ppb = product.pieces_per_box  or 1
    bpp = product.boxes_per_pallet or 1
    min_qty   = ppb * bpp
    increment = ppb * bpp  # 1 palet artış birimi
    if qty < min_qty:
        return None
    remainder = (qty - min_qty) % increment
    if remainder:
        qty -= remainder
        if qty < min_qty:
            return None
    boxes         = qty / ppb
    pallets       = boxes / bpp
    discount_rate = get_discount_rate(product, pallets)
    unit_price    = product.unit_price * (1 - discount_rate)
    return {
        "product":        product,
        "quantity":       qty,
        "boxes":          math.ceil(boxes),
        "pallets":        round(pallets, 2),
        "unit_price":     round(unit_price, 2),
        "original_price": round(product.unit_price, 2),
        "discount_rate":  discount_rate,
        "total_price":    round(unit_price * qty, 2),
    }


def build_basket_context(basket_items):
    tp   = sum(i["total_price"] for i in basket_items)
    tb   = sum(i["boxes"]       for i in basket_items)
    tpal = sum(i["pallets"]     for i in basket_items)
    p20  = min(round((tpal / 13) * 100, 1), 100) if tpal else 0
    p40  = min(round((tpal / 24) * 100, 1), 100) if tpal else 0
    return {
        "basket_items":          basket_items,
        "total_price":           round(tp, 2),
        "total_boxes":           tb,
        "total_pallets":         round(tpal, 2),
        "percent_20":            p20,
        "percent_40":            p40,
        "remaining_pallets_20":  round(max(13 - tpal, 0), 2),
        "remaining_pallets_40":  round(max(24 - tpal, 0), 2),
        "recommended_container": "20FT" if tpal <= 13 else ("40FT" if tpal <= 24 else "MULTI"),
    }


# =========================================================
# STATİK DOSYALAR — robots.txt, sitemap.xml
# =========================================================

@router.get("/robots.txt", include_in_schema=False)
def serve_robots():
    """robots.txt dosyasını static klasöründen serve eder."""
    robots_path = os.path.join(BASE_DIR, "static", "robots.txt")
    return FileResponse(robots_path, media_type="text/plain")


@router.get("/sitemap.xml", include_in_schema=False)
def serve_sitemap(db: Session = Depends(get_db)):
    """
    Dinamik XML sitemap üretir.
    - Tüm ürün sayfaları (7 dil)
    - Tüm yayında CMS sayfaları (7 dil)
    - Tüm kategori sayfaları (7 dil)
    - Statik sayfalar: anasayfa, iletişim, hakkımızda, quote-request (7 dil)
    """
    BASE_URL  = "https://henib2b.com"
    bugun     = date.today().isoformat()

    # Statik sayfa slug'ları (dile göre)
    STATIC_PATHS = {
        "homepage": {
            "en": "/", "tr": "/tr", "de": "/de",
            "fr": "/fr", "ar": "/ar", "ru": "/ru", "es": "/es",
        },
        "contact": {
            "en": "/contact", "tr": "/tr/iletisim", "de": "/de/kontakt",
            "fr": "/fr/contact", "ar": "/ar/contact", "ru": "/ru/kontakt", "es": "/es/contacto",
        },
        "about": {
            "en": "/about", "tr": "/tr/hakkimizda", "de": "/de/ueber-uns",
            "fr": "/fr/a-propos", "ar": "/ar/about", "ru": "/ru/o-nas", "es": "/es/sobre-nosotros",
        },
        "quote": {
            "en": "/quote-request", "tr": "/tr/quote-request", "de": "/de/quote-request",
            "fr": "/fr/quote-request", "ar": "/ar/quote-request", "ru": "/ru/quote-request", "es": "/es/quote-request",
        },
    }

    urls = []  # Her URL için {"loc": ..., "lastmod": ..., "changefreq": ..., "priority": ..., "alternates": [...]}

    # ── 1. Statik sayfalar ────────────────────────────────────────
    for page_key, lang_map in STATIC_PATHS.items():
        prio      = "1.0" if page_key == "homepage" else "0.5"
        lastmod   = bugun
        changefreq = "monthly"

        for lang, path in lang_map.items():
            # Tüm dil alternatifleri bu URL bloğuna eklenecek
            alternates = [
                {"lang": l, "href": BASE_URL + p}
                for l, p in lang_map.items()
            ]
            alternates.append({"lang": "x-default", "href": BASE_URL + lang_map["en"]})
            urls.append({
                "loc":        BASE_URL + path,
                "lastmod":    lastmod,
                "changefreq": changefreq,
                "priority":   prio,
                "alternates": alternates,
            })

    # ── 2. Ürün sayfaları ────────────────────────────────────────
    products = db.query(Product).filter(Product.slug.isnot(None)).all()
    for p in products:
        lang_map = {}
        for lang in SUPPORTED_LANGS:
            slug = p.get_slug_for(lang)
            if not slug:
                continue
            seg  = PRODUCT_SEGMENT.get(lang, "product")
            if lang == DEFAULT_LANG:
                path = f"/{seg}/{slug}"
            else:
                path = f"/{lang}/{seg}/{slug}"
            lang_map[lang] = path

        if not lang_map:
            continue

        alternates = [{"lang": l, "href": BASE_URL + path} for l, path in lang_map.items()]
        if "en" in lang_map:
            alternates.append({"lang": "x-default", "href": BASE_URL + lang_map["en"]})

        # updated_at varsa gerçek tarihi kullan, yoksa bugünün tarihi
        product_lastmod = p.updated_at.date().isoformat() if p.updated_at else bugun

        for lang, path in lang_map.items():
            urls.append({
                "loc":        BASE_URL + path,
                "lastmod":    product_lastmod,
                "changefreq": "weekly",
                "priority":   "0.7",
                "alternates": alternates,
            })

    # ── 3. CMS sayfa sayfaları ───────────────────────────────────
    pages = db.query(Page).filter(Page.is_published == 1).all()
    for pg in pages:
        lastmod  = pg.updated_at.date().isoformat() if pg.updated_at else bugun
        lang_map = {}
        for lang in SUPPORTED_LANGS:
            slug = pg.get_slug_for(lang)
            if not slug:
                continue
            if lang == DEFAULT_LANG:
                path = f"/{slug}"
            else:
                path = f"/{lang}/{slug}"
            lang_map[lang] = path

        if not lang_map:
            continue

        alternates = [{"lang": l, "href": BASE_URL + path} for l, path in lang_map.items()]
        if "en" in lang_map:
            alternates.append({"lang": "x-default", "href": BASE_URL + lang_map["en"]})

        for lang, path in lang_map.items():
            urls.append({
                "loc":        BASE_URL + path,
                "lastmod":    lastmod,
                "changefreq": "monthly",
                "priority":   "0.5",
                "alternates": alternates,
            })

    # ── 4. Kategori sayfaları ────────────────────────────────────
    for cat_key in CATEGORY_LABELS:
        lang_map = {}
        for lang in SUPPORTED_LANGS:
            cat_slugs = CATEGORY_SLUGS_BY_LANG.get(lang, CATEGORY_SLUGS_BY_LANG["en"])
            cat_slug  = cat_slugs.get(cat_key, "")
            if not cat_slug:
                continue
            seg = CATEGORY_SEGMENT.get(lang, "category")
            if lang == DEFAULT_LANG:
                path = f"/{seg}/{cat_slug}"
            else:
                path = f"/{lang}/{seg}/{cat_slug}"
            lang_map[lang] = path

        if not lang_map:
            continue

        alternates = [{"lang": l, "href": BASE_URL + path} for l, path in lang_map.items()]
        if "en" in lang_map:
            alternates.append({"lang": "x-default", "href": BASE_URL + lang_map["en"]})

        for lang, path in lang_map.items():
            urls.append({
                "loc":        BASE_URL + path,
                "lastmod":    bugun,
                "changefreq": "weekly",
                "priority":   "0.8",
                "alternates": alternates,
            })

    # ── XML oluştur ──────────────────────────────────────────────
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">'
    )

    for entry in urls:
        xml_parts.append("  <url>")
        xml_parts.append(f"    <loc>{entry['loc']}</loc>")
        xml_parts.append(f"    <lastmod>{entry['lastmod']}</lastmod>")
        xml_parts.append(f"    <changefreq>{entry['changefreq']}</changefreq>")
        xml_parts.append(f"    <priority>{entry['priority']}</priority>")
        for alt in entry.get("alternates", []):
            xml_parts.append(
                f'    <xhtml:link rel="alternate" hreflang="{alt["lang"]}" href="{alt["href"]}"/>'
            )
        xml_parts.append("  </url>")

    xml_parts.append("</urlset>")
    xml_content = "\n".join(xml_parts)

    return Response(content=xml_content, media_type="application/xml")


# HOMEPAGE  /  /tr  /de  /fr  /ar  /ru  /es
# =========================================================

@router.get("/")
def homepage_en(request: Request, db: Session = Depends(get_db)):
    return _homepage(request, "en", db)

@router.get("/tr")
def homepage_tr(request: Request, db: Session = Depends(get_db)):
    return _homepage(request, "tr", db)

@router.get("/de")
def homepage_de(request: Request, db: Session = Depends(get_db)):
    return _homepage(request, "de", db)

@router.get("/fr")
def homepage_fr(request: Request, db: Session = Depends(get_db)):
    return _homepage(request, "fr", db)

@router.get("/ar")
def homepage_ar(request: Request, db: Session = Depends(get_db)):
    return _homepage(request, "ar", db)

@router.get("/ru")
def homepage_ru(request: Request, db: Session = Depends(get_db)):
    return _homepage(request, "ru", db)

@router.get("/es")
def homepage_es(request: Request, db: Session = Depends(get_db)):
    return _homepage(request, "es", db)


def _homepage(request: Request, lang: str, db=None):
    ctx = common_ctx(request, lang, db=db)
    ctx["lang_urls"] = {
        "en": "/", "tr": "/tr", "de": "/de", "fr": "/fr",
        "ar": "/ar", "ru": "/ru", "es": "/es",
    }
    ctx["active_page"] = "home"
    # Query string olmadan temiz canonical URL (EN → /, diğer diller → /lang)
    lang_prefix = "" if lang == "en" else f"/{lang}"
    ctx["canonical_url"] = f"https://henib2b.com{lang_prefix}/"
    return templates.TemplateResponse("homepage.html", ctx)


# =========================================================
# SHOWROOM  /products  /tr/urunler  ...
# =========================================================

@router.get("/products")
def showroom_en(request: Request, db: Session = Depends(get_db)):
    return _showroom(request, "en", db)

@router.get("/tr/urunler")
def showroom_tr(request: Request, db: Session = Depends(get_db)):
    return _showroom(request, "tr", db)

@router.get("/de/produkte")
def showroom_de(request: Request, db: Session = Depends(get_db)):
    return _showroom(request, "de", db)

@router.get("/fr/produits")
def showroom_fr(request: Request, db: Session = Depends(get_db)):
    return _showroom(request, "fr", db)

@router.get("/ar/products")
def showroom_ar(request: Request, db: Session = Depends(get_db)):
    return _showroom(request, "ar", db)

@router.get("/ru/produkty")
def showroom_ru(request: Request, db: Session = Depends(get_db)):
    return _showroom(request, "ru", db)

@router.get("/es/productos")
def showroom_es(request: Request, db: Session = Depends(get_db)):
    return _showroom(request, "es", db)


def _showroom(request: Request, lang: str, db: Session):
    # Arama filtresi — q parametresi varsa ürün adı veya slug'a göre filtrele
    q = (request.query_params.get("q") or "").strip().lower()
    products = db.query(Product).all()
    if q:
        filtered = []
        for p in products:
            trans = p.get_translation(lang)
            name  = (trans.name if trans else "") or p.slug or ""
            if q in name.lower() or q in (p.slug or "").lower():
                filtered.append(p)
        products = filtered
    cart     = request.session.get("cart", {})

    products_ctx = []
    for p in products:
        trans   = p.get_translation(lang)
        pid_str = str(p.id)
        cart_info = {}
        if pid_str in cart:
            item = compute_basket_item(p, cart[pid_str])
            if item:
                cart_info = {
                    "qty":           item["quantity"],
                    "unit_price":    item["unit_price"],
                    "discount_rate": item["discount_rate"],
                }
        lang_slug = p.get_slug_for(lang)
        products_ctx.append({
            "product":          p,
            "trans":            trans,
            "cart_info":        cart_info,
            "qty_in_cart":      cart.get(pid_str, 0),
            "min_qty":          (p.pieces_per_box or 1) * (p.boxes_per_pallet or 1),
            "increment":        (p.pieces_per_box or 1) * (p.boxes_per_pallet or 1),
            "add_to_cart_url":  add_to_cart_url(lang),
            "update_cart_url":  update_cart_url(lang),
            "product_url":      product_url(lang, lang_slug) if lang_slug else "#",
            "category_label":   get_category_label(p.category or "", lang),
            "category_url":     category_url(lang, p.category or "") if p.category else None,
        })

    ctx = common_ctx(request, lang, db=db)
    ctx["products_ctx"] = products_ctx
    ctx["active_page"] = "showroom"
    ctx["search_query"] = request.query_params.get("q", "")
    # Query string olmadan temiz canonical URL
    ctx["canonical_url"] = f"https://henib2b.com{request.url.path}"
    return templates.TemplateResponse("showroom.html", ctx)


# =========================================================
# PRODUCT DETAIL
# /product/{slug}          → EN
# /tr/urun/{slug}          → TR
# /de/produkt/{slug}       → DE
# /fr/produit/{slug}       → FR
# /ar/muntaj/{slug}        → AR
# /ru/produkt/{slug}       → RU
# /es/producto/{slug}      → ES
# =========================================================

# =========================================================
# ÜRÜN DEĞERLENDİRME API
# =========================================================

class _RatingPayload(BaseModel):
    browser_id: str
    rating: int

@router.post("/api/rate-product/{product_id}")
def api_rate_product(product_id: int, payload: _RatingPayload, db: Session = Depends(get_db)):
    """Tarayıcı başına bir kez ürün değerlendirmesi kaydeder ve güncel ortalamayı döner."""
    # Gelen değerleri doğrula
    if not payload.browser_id or not (1 <= payload.rating <= 5):
        raise HTTPException(status_code=400, detail="Geçersiz istek")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    # Aynı tarayıcı daha önce oy kullandıysa engelle
    existing = db.query(ProductRating).filter(
        ProductRating.product_id == product_id,
        ProductRating.browser_id == payload.browser_id,
    ).first()
    if existing:
        return JSONResponse({
            "ok": False,
            "already_voted": True,
            "rating": round(product.rating or 0, 1),
            "count": product.rating_count or 0,
        })

    # Yeni oyu kaydet
    db.add(ProductRating(
        product_id=product_id,
        browser_id=payload.browser_id,
        rating=payload.rating,
    ))
    db.flush()

    # Tüm oylardan ortalama hesapla
    all_ratings = db.query(ProductRating).filter(ProductRating.product_id == product_id).all()
    count = len(all_ratings)
    avg   = sum(r.rating for r in all_ratings) / count

    product.rating       = round(avg, 2)
    product.rating_count = count
    db.commit()

    return JSONResponse({
        "ok":     True,
        "rating": round(avg, 1),
        "count":  count,
    })


@router.get("/product/{slug}")
def product_en(slug: str, request: Request, db: Session = Depends(get_db)):
    return _product_detail(request, "en", slug, db)

@router.get("/tr/urun/{slug}")
def product_tr(slug: str, request: Request, db: Session = Depends(get_db)):
    return _product_detail(request, "tr", slug, db)

@router.get("/de/produkt/{slug}")
def product_de(slug: str, request: Request, db: Session = Depends(get_db)):
    return _product_detail(request, "de", slug, db)

@router.get("/fr/produit/{slug}")
def product_fr(slug: str, request: Request, db: Session = Depends(get_db)):
    return _product_detail(request, "fr", slug, db)

@router.get("/ar/muntaj/{slug}")
def product_ar(slug: str, request: Request, db: Session = Depends(get_db)):
    return _product_detail(request, "ar", slug, db)

@router.get("/ru/produkt/{slug}")
def product_ru(slug: str, request: Request, db: Session = Depends(get_db)):
    return _product_detail(request, "ru", slug, db)

@router.get("/es/producto/{slug}")
def product_es(slug: str, request: Request, db: Session = Depends(get_db)):
    return _product_detail(request, "es", slug, db)


def _product_detail(request: Request, lang: str, slug: str, db: Session):
    # 1. Dile özgü translation slug'ına bak
    trans_row = db.query(ProductTranslation).filter(
        ProductTranslation.slug == slug,
        ProductTranslation.lang == lang
    ).first()

    if trans_row:
        product = trans_row.product
    else:
        # 2. Evrensel Product.slug (EN fallback)
        product = db.query(Product).filter(Product.slug == slug).first()

    # 3. Numeric ID eski fallback
    if not product and slug.isdigit():
        product = db.query(Product).filter(Product.id == int(slug)).first()
        if product:
            correct = product.get_slug_for(lang)
            return RedirectResponse(product_url(lang, correct), status_code=301)

    if not product:
        return RedirectResponse(showroom_url(lang), status_code=303)

    # Doğru slug'la geldiyse ama dile özgü slug varsa → 301
    trans_check = product.get_translation(lang)
    if trans_check and trans_check.slug and trans_check.slug != slug:
        return RedirectResponse(product_url(lang, trans_check.slug), status_code=301)

    trans      = product.get_translation(lang)
    meta_title = (trans.meta_title if trans else None) or \
                 f"{trans.name if trans else slug} | Heni Showroom"
    meta_desc  = (trans.meta_description if trans else None) or \
                 (trans.short_description if trans else "") or ""

    discount_tiers = [
        {"label": "1+ Palet", "rate": product.discount_1_pallet},
        {"label": "2+ Palet", "rate": product.discount_2_pallet},
        {"label": "3+ Palet", "rate": product.discount_3_pallet},
        {"label": "4+ Palet", "rate": product.discount_4_pallet},
        {"label": "5+ Palet", "rate": product.discount_5_plus_pallet},
    ]
    discount_tiers = [t for t in discount_tiers if (t["rate"] or 0) > 0]
    export_list    = [c.strip() for c in (product.export_countries or "").split(",") if c.strip()]

    cart        = request.session.get("cart", {})
    pid_str     = str(product.id)
    qty_in_cart = cart.get(pid_str, 0)
    cart_info   = {}
    if qty_in_cart:
        item = compute_basket_item(product, qty_in_cart)
        if item:
            cart_info = {"unit_price": item["unit_price"], "discount_rate": item["discount_rate"]}

    min_qty   = (product.pieces_per_box or 1) * (product.boxes_per_pallet or 1)
    increment = (product.pieces_per_box or 1) * (product.boxes_per_pallet or 1)  # 1 palet artış birimi
    # Query string olmadan temiz canonical URL — base.html bu değişkeni kullanır
    canonical_url = product_url(lang, product.get_slug_for(lang))

    # Aynı kategorideki ilgili ürünleri çek (mevcut ürün hariç, en fazla 4 adet)
    related_ctx = []
    if product.category:
        related_products = (
            db.query(Product)
            .filter(Product.category == product.category, Product.id != product.id)
            .limit(4)
            .all()
        )
        for rp in related_products:
            rp_trans    = rp.get_translation(lang)
            rp_slug     = rp.get_slug_for(lang)
            rp_pid_str  = str(rp.id)
            rp_cart_info = {}
            if rp_pid_str in cart:
                rp_item = compute_basket_item(rp, cart[rp_pid_str])
                if rp_item:
                    rp_cart_info = {
                        "unit_price":    rp_item["unit_price"],
                        "discount_rate": rp_item["discount_rate"],
                    }
            related_ctx.append({
                "product":         rp,
                "trans":           rp_trans,
                "cart_info":       rp_cart_info,
                "qty_in_cart":     cart.get(rp_pid_str, 0),
                "min_qty":         (rp.pieces_per_box or 1) * (rp.boxes_per_pallet or 1),
                "increment":       (rp.pieces_per_box or 1) * (rp.boxes_per_pallet or 1),
                "update_cart_url": update_cart_url(lang),
                "product_url":     product_url(lang, rp_slug) if rp_slug else "#",
            })

    ctx = common_ctx(request, lang, product=product, db=db)
    ctx["active_page"] = "showroom"
    ctx.update({
        "product":          product,
        "trans":            trans,
        "meta_title":       meta_title,
        "meta_description": meta_desc,
        "canonical_url":    canonical_url,
        "discount_tiers":   discount_tiers,
        "export_list":      export_list,
        "qty_in_cart":      qty_in_cart,
        "cart_info":        cart_info,
        "min_qty":          min_qty,
        "increment":        increment,
        "add_to_cart_url":  add_to_cart_url(lang),
        "update_cart_url":  update_cart_url(lang),
        "category_label":   get_category_label(product.category or "", lang),
        "category_url":     category_url(lang, product.category or "") if product.category else None,
        "related_ctx":      related_ctx,
    })
    return templates.TemplateResponse("product_detail.html", ctx)


# =========================================================
# CATEGORY FILTER
# =========================================================

@router.get("/category/{cat_slug}")
def category_en(cat_slug: str, request: Request, db: Session = Depends(get_db)):
    return _category(request, "en", cat_slug, db)

@router.get("/tr/kategori/{cat_slug}")
def category_tr(cat_slug: str, request: Request, db: Session = Depends(get_db)):
    return _category(request, "tr", cat_slug, db)

@router.get("/de/kategorie/{cat_slug}")
def category_de(cat_slug: str, request: Request, db: Session = Depends(get_db)):
    return _category(request, "de", cat_slug, db)

@router.get("/fr/categorie/{cat_slug}")
def category_fr(cat_slug: str, request: Request, db: Session = Depends(get_db)):
    return _category(request, "fr", cat_slug, db)

@router.get("/ar/category/{cat_slug}")
def category_ar(cat_slug: str, request: Request, db: Session = Depends(get_db)):
    return _category(request, "ar", cat_slug, db)

@router.get("/ru/kategoriya/{cat_slug}")
def category_ru(cat_slug: str, request: Request, db: Session = Depends(get_db)):
    return _category(request, "ru", cat_slug, db)

@router.get("/es/categoria/{cat_slug}")
def category_es(cat_slug: str, request: Request, db: Session = Depends(get_db)):
    return _category(request, "es", cat_slug, db)


def _category(request: Request, lang: str, cat_slug: str, db: Session):
    reverse = SLUG_TO_CATEGORY_BY_LANG.get(lang, SLUG_TO_CATEGORY_BY_LANG["en"])
    cat_key = reverse.get(cat_slug)
    if not cat_key:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")

    products = db.query(Product).filter(Product.category == cat_key).all()
    cart     = request.session.get("cart", {})

    products_ctx = []
    for p in products:
        trans   = p.get_translation(lang)
        pid_str = str(p.id)
        cart_info = {}
        if pid_str in cart:
            item = compute_basket_item(p, cart[pid_str])
            if item:
                cart_info = {
                    "qty":           item["quantity"],
                    "unit_price":    item["unit_price"],
                    "discount_rate": item["discount_rate"],
                }
        lang_slug = p.get_slug_for(lang)
        products_ctx.append({
            "product":          p,
            "trans":            trans,
            "cart_info":        cart_info,
            "qty_in_cart":      cart.get(pid_str, 0),
            "min_qty":          (p.pieces_per_box or 1) * (p.boxes_per_pallet or 1),
            "increment":        (p.pieces_per_box or 1) * (p.boxes_per_pallet or 1),
            "add_to_cart_url":  add_to_cart_url(lang),
            "update_cart_url":  update_cart_url(lang),
            "product_url":      product_url(lang, lang_slug) if lang_slug else "#",
            "category_label":   get_category_label(p.category or "", lang),
            "category_url":     category_url(lang, p.category or "") if p.category else None,
        })

    cat_label = get_category_label(cat_key, lang)
    lang_urls = {l: category_url(l, cat_key) for l in SUPPORTED_LANGS}

    # CategoryContent CMS — model varsa kullan, yoksa boş
    cat_content = None
    cat_trans   = None
    cat_faqs    = []
    meta_title  = f"{cat_label} | Heni"
    meta_desc   = ""
    if db:
        try:
            from app.models import CategoryContent
            cat_content = db.query(CategoryContent).filter(
                CategoryContent.category_key == cat_key
            ).first()
            if cat_content:
                cat_trans  = cat_content.get_translation(lang)
                cat_faqs   = [f for f in cat_content.faqs if f.lang == lang]
                cat_faqs.sort(key=lambda x: x.sort_order)
                if cat_trans and cat_trans.meta_title:
                    meta_title = cat_trans.meta_title
                if cat_trans and cat_trans.meta_description:
                    meta_desc = cat_trans.meta_description
        except Exception:
            pass

    ctx = common_ctx(request, lang, db=db)
    ctx["active_page"] = "showroom"
    ctx.update({
        "products_ctx":     products_ctx,
        "page_title":       cat_label,
        "is_category_page": True,
        "current_category": cat_key,
        "cat_slug":         cat_slug,
        "cat_content":      cat_content,
        "cat_trans":        cat_trans,
        "cat_faqs":         cat_faqs,
        "meta_title":       meta_title,
        "meta_description": meta_desc,
        "lang_urls":        lang_urls,
        # Query string olmadan temiz canonical URL
        "canonical_url":    f"https://henib2b.com{request.url.path}",
    })
    return templates.TemplateResponse("showroom.html", ctx)


# =========================================================
# BASKET
# =========================================================

@router.get("/basket")
def basket_en(request: Request, db: Session = Depends(get_db)):
    return _basket(request, "en", db)

@router.get("/tr/sepet")
def basket_tr(request: Request, db: Session = Depends(get_db)):
    return _basket(request, "tr", db)

@router.get("/de/warenkorb")
def basket_de(request: Request, db: Session = Depends(get_db)):
    return _basket(request, "de", db)

@router.get("/fr/panier")
def basket_fr(request: Request, db: Session = Depends(get_db)):
    return _basket(request, "fr", db)

@router.get("/ar/salla")
def basket_ar(request: Request, db: Session = Depends(get_db)):
    return _basket(request, "ar", db)

@router.get("/ru/korzina")
def basket_ru(request: Request, db: Session = Depends(get_db)):
    return _basket(request, "ru", db)

@router.get("/es/carrito")
def basket_es(request: Request, db: Session = Depends(get_db)):
    return _basket(request, "es", db)


def _basket(request: Request, lang: str, db: Session):
    cart         = request.session.get("cart", {})
    basket_items = []
    for pid_str, qty in cart.items():
        product = db.query(Product).filter(Product.id == int(pid_str)).first()
        if not product:
            continue
        item = compute_basket_item(product, qty)
        if item:
            item["trans"] = product.get_translation(lang)
            basket_items.append(item)

    ctx = build_basket_context(basket_items)
    ctx.update(common_ctx(request, lang, db=db))
    ctx["active_page"] = "basket"
    # Dil seçicinin her dil için sepet URL'sine yönlendirmesi için override
    ctx["lang_urls"] = {l: basket_url(l) for l in SUPPORTED_LANGS}
    ctx.update({
        "update_cart_url": update_cart_url(lang),
        "remove_cart_url": remove_cart_url(lang),
        "quote_url":       quote_url(lang),
    })
    return templates.TemplateResponse("basket.html", ctx)


# =========================================================
# ADD TO CART
# =========================================================

@router.post("/add-to-cart")
def add_cart_en(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _add_to_cart(request, "en", product_id, quantity, db)

@router.post("/tr/add-to-cart")
def add_cart_tr(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _add_to_cart(request, "tr", product_id, quantity, db)

@router.post("/de/add-to-cart")
def add_cart_de(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _add_to_cart(request, "de", product_id, quantity, db)

@router.post("/fr/add-to-cart")
def add_cart_fr(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _add_to_cart(request, "fr", product_id, quantity, db)

@router.post("/ar/add-to-cart")
def add_cart_ar(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _add_to_cart(request, "ar", product_id, quantity, db)

@router.post("/ru/add-to-cart")
def add_cart_ru(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _add_to_cart(request, "ru", product_id, quantity, db)

@router.post("/es/add-to-cart")
def add_cart_es(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _add_to_cart(request, "es", product_id, quantity, db)


def _add_to_cart(request, lang, product_id, quantity, db):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse(showroom_url(lang), status_code=303)
    ppb = product.pieces_per_box  or 1
    bpp = product.boxes_per_pallet or 1
    min_qty   = ppb * bpp
    increment = ppb * bpp  # 1 palet artış birimi
    if quantity < min_qty:
        quantity = min_qty
    remainder = (quantity - min_qty) % increment
    if remainder:
        quantity -= remainder
    cart      = request.session.get("cart", {})
    key       = str(product_id)
    cart[key] = cart.get(key, 0) + quantity
    request.session["cart"] = cart
    # AJAX isteği ise JSON dön, normal form ise redirect
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        return JSONResponse({"success": True, "cart_count": len(cart)})
    return RedirectResponse(showroom_url(lang), status_code=303)


# =========================================================
# UPDATE CART
# =========================================================

@router.post("/update-cart")
def update_cart_en(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _update_cart(request, "en", product_id, quantity, db)

@router.post("/tr/update-cart")
def update_cart_tr(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _update_cart(request, "tr", product_id, quantity, db)

@router.post("/de/update-cart")
def update_cart_de(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _update_cart(request, "de", product_id, quantity, db)

@router.post("/fr/update-cart")
def update_cart_fr(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _update_cart(request, "fr", product_id, quantity, db)

@router.post("/ar/update-cart")
def update_cart_ar(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _update_cart(request, "ar", product_id, quantity, db)

@router.post("/ru/update-cart")
def update_cart_ru(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _update_cart(request, "ru", product_id, quantity, db)

@router.post("/es/update-cart")
def update_cart_es(request: Request, product_id: int = Form(...), quantity: int = Form(...), db: Session = Depends(get_db)):
    return _update_cart(request, "es", product_id, quantity, db)


def _update_cart(request, lang, product_id, quantity, db):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse(basket_url(lang), status_code=303)
    ppb = product.pieces_per_box  or 1
    bpp = product.boxes_per_pallet or 1
    min_qty   = ppb * bpp
    increment = ppb * bpp  # 1 palet artış birimi
    cart = request.session.get("cart", {})
    key  = str(product_id)
    if quantity <= 0:
        cart.pop(key, None)
    else:
        if quantity < min_qty:
            quantity = min_qty
        remainder = (quantity - min_qty) % increment
        if remainder:
            quantity -= remainder
        cart[key] = quantity
    request.session["cart"] = cart
    # AJAX isteği ise JSON dön, normal form ise redirect
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        return JSONResponse({"success": True, "cart_count": len(cart), "qty": cart.get(key, 0)})
    return RedirectResponse(basket_url(lang), status_code=303)


# =========================================================
# REMOVE FROM CART
# =========================================================

@router.post("/remove-from-cart")
def remove_cart_en(request: Request, product_id: int = Form(...)):
    return _remove_cart(request, "en", product_id)

@router.post("/tr/remove-from-cart")
def remove_cart_tr(request: Request, product_id: int = Form(...)):
    return _remove_cart(request, "tr", product_id)

@router.post("/de/remove-from-cart")
def remove_cart_de(request: Request, product_id: int = Form(...)):
    return _remove_cart(request, "de", product_id)

@router.post("/fr/remove-from-cart")
def remove_cart_fr(request: Request, product_id: int = Form(...)):
    return _remove_cart(request, "fr", product_id)

@router.post("/ar/remove-from-cart")
def remove_cart_ar(request: Request, product_id: int = Form(...)):
    return _remove_cart(request, "ar", product_id)

@router.post("/ru/remove-from-cart")
def remove_cart_ru(request: Request, product_id: int = Form(...)):
    return _remove_cart(request, "ru", product_id)

@router.post("/es/remove-from-cart")
def remove_cart_es(request: Request, product_id: int = Form(...)):
    return _remove_cart(request, "es", product_id)


def _remove_cart(request, lang, product_id):
    cart = request.session.get("cart", {})
    cart.pop(str(product_id), None)
    request.session["cart"] = cart
    return RedirectResponse(basket_url(lang), status_code=303)


# =========================================================
# SEARCH API — canlı arama dropdown için JSON endpoint
# =========================================================

@router.get("/api/search")
def api_search(request: Request, q: str = "", lang: str = "en", db: Session = Depends(get_db)):
    """Ürün adı veya slug'a göre arama — JSON liste döner."""
    q = q.strip().lower()
    if len(q) < 2:
        return JSONResponse([])
    products = db.query(Product).all()
    results  = []
    for p in products:
        trans = p.get_translation(lang)
        name  = (trans.name if trans else "") or p.slug or ""
        if q in name.lower() or q in (p.slug or "").lower():
            lang_slug = p.get_slug_for(lang)
            results.append({
                "id":    p.id,
                "name":  name,
                "image": p.image,
                "price": p.unit_price,
                "url":   product_url(lang, lang_slug) if lang_slug else "#",
            })
        if len(results) >= 8:
            break
    return JSONResponse(results)


# =========================================================
# QUOTE REQUEST
# =========================================================

@router.post("/quote-request")
def quote_en(request: Request, company_name: str = Form(...), contact_person: str = Form(...), email: str = Form(...), phone: str = Form(None), country: str = Form(None), db: Session = Depends(get_db)):
    return _quote(request, "en", company_name, contact_person, email, phone, country, db)

@router.post("/tr/quote-request")
def quote_tr(request: Request, company_name: str = Form(...), contact_person: str = Form(...), email: str = Form(...), phone: str = Form(None), country: str = Form(None), db: Session = Depends(get_db)):
    return _quote(request, "tr", company_name, contact_person, email, phone, country, db)

@router.post("/de/quote-request")
def quote_de(request: Request, company_name: str = Form(...), contact_person: str = Form(...), email: str = Form(...), phone: str = Form(None), country: str = Form(None), db: Session = Depends(get_db)):
    return _quote(request, "de", company_name, contact_person, email, phone, country, db)

@router.post("/fr/quote-request")
def quote_fr(request: Request, company_name: str = Form(...), contact_person: str = Form(...), email: str = Form(...), phone: str = Form(None), country: str = Form(None), db: Session = Depends(get_db)):
    return _quote(request, "fr", company_name, contact_person, email, phone, country, db)

@router.post("/ar/quote-request")
def quote_ar(request: Request, company_name: str = Form(...), contact_person: str = Form(...), email: str = Form(...), phone: str = Form(None), country: str = Form(None), db: Session = Depends(get_db)):
    return _quote(request, "ar", company_name, contact_person, email, phone, country, db)

@router.post("/ru/quote-request")
def quote_ru(request: Request, company_name: str = Form(...), contact_person: str = Form(...), email: str = Form(...), phone: str = Form(None), country: str = Form(None), db: Session = Depends(get_db)):
    return _quote(request, "ru", company_name, contact_person, email, phone, country, db)

@router.post("/es/quote-request")
def quote_es(request: Request, company_name: str = Form(...), contact_person: str = Form(...), email: str = Form(...), phone: str = Form(None), country: str = Form(None), db: Session = Depends(get_db)):
    return _quote(request, "es", company_name, contact_person, email, phone, country, db)


def _quote(request, lang, company_name, contact_person, email, phone, country, db):
    cart = request.session.get("cart", {})
    if not cart:
        raise HTTPException(status_code=400, detail="Cart is empty")
    basket_items = []
    total_price  = 0
    for pid_str, qty in cart.items():
        product = db.query(Product).filter(Product.id == int(pid_str)).first()
        if not product:
            continue
        item = compute_basket_item(product, qty)
        if not item:
            continue
        trans = product.get_translation(lang)
        total_price += item["total_price"]
        basket_items.append({
            "product_id":     product.id,
            "product_name":   trans.name if trans else (product.slug or ""),
            "quantity":       item["quantity"],
            "boxes":          item["boxes"],
            "pallets":        item["pallets"],
            "unit_price":     item["unit_price"],
            "original_price": item["original_price"],
            "discount_rate":  item["discount_rate"],
            "total_price":    item["total_price"],
        })
    currency = LANG_CURRENCY.get(lang, "USD")
    quote = QuoteRequest(
        company_name=company_name,
        contact_person=contact_person,
        email=email,
        phone=phone,
        country=country,
        total_price=round(total_price, 2),
        currency=currency,
        cart_data=json.dumps(basket_items),
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    request.session["cart"] = {}
    price_formatted = format_price(total_price, lang, get_rates())
    site = _get_site_settings(db, lang)
    ui   = UI.get(lang, UI["en"])
    return templates.TemplateResponse("quote_success.html", {
        "request":        request,
        "lang":           lang,
        "ui":             ui,
        "site":           site,
        "quote_id":       quote.id,
        "total_price":    round(total_price, 2),
        "price_formatted": price_formatted,
        "email":          email,
        "home_url":       home_root_url(lang),
        "showroom_url":   showroom_url(lang),
    })


# =========================================================
# LANDING PAGE TEKLİF FORMU  — sepet gerektirmez, QuoteRequest'e kaydeder
# =========================================================

def _landing_quote(request: Request, lang: str,
                   company_name: str, contact_person: str, email: str,
                   phone: str, message: str, source_page: str, country: str,
                   db: Session):
    # Landing page'den gelen teklif talebini kaydeder; sepet zorunluluğu yoktur
    currency = LANG_CURRENCY.get(lang, "USD")
    cart_payload = json.dumps([{
        "source": source_page or "landing",
        "message": message or ""
    }])
    quote = QuoteRequest(
        company_name=company_name,
        contact_person=contact_person,
        email=email,
        phone=phone or "",
        country=country or "",
        total_price=0.0,
        currency=currency,
        cart_data=cart_payload,
    )
    db.add(quote)
    db.commit()
    # Başarı sayfasını render et — dile göre anasayfa URL'si ve UI metinleri ilet
    site = _get_site_settings(db, lang)
    ui   = UI.get(lang, UI["en"])
    return templates.TemplateResponse("landing_quote_success.html", {
        "request":  request,
        "lang":     lang,
        "ui":       ui,
        "email":    email,
        "site":     site,
        "home_url": home_root_url(lang),
    })


@router.post("/landing-quote")
def landing_quote_en(request: Request,
                     company_name: str = Form(...), contact_person: str = Form(...),
                     email: str = Form(...), phone: str = Form(""),
                     message: str = Form(""), source_page: str = Form(""),
                     country: str = Form(""),
                     db: Session = Depends(get_db)):
    return _landing_quote(request, "en", company_name, contact_person, email, phone, message, source_page, country, db)

@router.post("/tr/landing-quote")
def landing_quote_tr(request: Request,
                     company_name: str = Form(...), contact_person: str = Form(...),
                     email: str = Form(...), phone: str = Form(""),
                     message: str = Form(""), source_page: str = Form(""),
                     country: str = Form(""),
                     db: Session = Depends(get_db)):
    return _landing_quote(request, "tr", company_name, contact_person, email, phone, message, source_page, country, db)

@router.post("/de/landing-quote")
def landing_quote_de(request: Request,
                     company_name: str = Form(...), contact_person: str = Form(...),
                     email: str = Form(...), phone: str = Form(""),
                     message: str = Form(""), source_page: str = Form(""),
                     country: str = Form(""),
                     db: Session = Depends(get_db)):
    return _landing_quote(request, "de", company_name, contact_person, email, phone, message, source_page, country, db)

@router.post("/fr/landing-quote")
def landing_quote_fr(request: Request,
                     company_name: str = Form(...), contact_person: str = Form(...),
                     email: str = Form(...), phone: str = Form(""),
                     message: str = Form(""), source_page: str = Form(""),
                     country: str = Form(""),
                     db: Session = Depends(get_db)):
    return _landing_quote(request, "fr", company_name, contact_person, email, phone, message, source_page, country, db)

@router.post("/ar/landing-quote")
def landing_quote_ar(request: Request,
                     company_name: str = Form(...), contact_person: str = Form(...),
                     email: str = Form(...), phone: str = Form(""),
                     message: str = Form(""), source_page: str = Form(""),
                     country: str = Form(""),
                     db: Session = Depends(get_db)):
    return _landing_quote(request, "ar", company_name, contact_person, email, phone, message, source_page, country, db)

@router.post("/ru/landing-quote")
def landing_quote_ru(request: Request,
                     company_name: str = Form(...), contact_person: str = Form(...),
                     email: str = Form(...), phone: str = Form(""),
                     message: str = Form(""), source_page: str = Form(""),
                     country: str = Form(""),
                     db: Session = Depends(get_db)):
    return _landing_quote(request, "ru", company_name, contact_person, email, phone, message, source_page, country, db)

@router.post("/es/landing-quote")
def landing_quote_es(request: Request,
                     company_name: str = Form(...), contact_person: str = Form(...),
                     email: str = Form(...), phone: str = Form(""),
                     message: str = Form(""), source_page: str = Form(""),
                     country: str = Form(""),
                     db: Session = Depends(get_db)):
    return _landing_quote(request, "es", company_name, contact_person, email, phone, message, source_page, country, db)


# =========================================================
# CMS SAYFALARI  /{slug}  /tr/{slug}  /de/{slug} ...
# =========================================================
# ⚠️ Bu route'lar dosyanın EN SONUNDA olmalı; /{slug} pattern'i
# diğer sabit route'ları gölgelemesin diye.

@router.get("/{slug}")
def page_en(slug: str, request: Request, db: Session = Depends(get_db)):
    return _page_detail(request, "en", slug, db)

@router.get("/tr/{slug}")
def page_tr(slug: str, request: Request, db: Session = Depends(get_db)):
    return _page_detail(request, "tr", slug, db)

@router.get("/de/{slug}")
def page_de(slug: str, request: Request, db: Session = Depends(get_db)):
    return _page_detail(request, "de", slug, db)

@router.get("/fr/{slug}")
def page_fr(slug: str, request: Request, db: Session = Depends(get_db)):
    return _page_detail(request, "fr", slug, db)

@router.get("/ar/{slug}")
def page_ar(slug: str, request: Request, db: Session = Depends(get_db)):
    return _page_detail(request, "ar", slug, db)

@router.get("/ru/{slug}")
def page_ru(slug: str, request: Request, db: Session = Depends(get_db)):
    return _page_detail(request, "ru", slug, db)

@router.get("/es/{slug}")
def page_es(slug: str, request: Request, db: Session = Depends(get_db)):
    return _page_detail(request, "es", slug, db)


def _page_detail(request: Request, lang: str, slug: str, db: Session):
    # 1. Dile özgü PageTranslation.slug ile ara
    trans_row = db.query(PageTranslation).filter(
        PageTranslation.slug == slug,
        PageTranslation.lang == lang,
    ).first()

    if trans_row:
        page = trans_row.page
    else:
        # 2. EN master slug ile ara (Page.slug)
        page = db.query(Page).filter(Page.slug == slug).first()

    # Sayfa bulunamadı veya yayında değil → 404
    if not page or not page.is_published:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadı")

    # Dile uygun translation al; yoksa EN fallback
    trans = page.get_translation(lang)

    # FAQ'ları dile göre filtrele
    faqs = [f for f in page.faqs if f.lang == lang] or \
           [f for f in page.faqs if f.lang == "en"]

    meta_title = (trans.meta_title if trans else None) or \
                 (trans.title if trans else slug) + " | Heni"
    meta_desc  = (trans.meta_description if trans else None) or ""

    # Dil seçicisi için her dil URL'sini page translation slug'larından oluştur
    def _page_lang_url(lc: str) -> str:
        if lc == "en":
            return f"/{page.slug}"
        t = page.get_translation(lc)
        if t and t.slug:
            return f"/{lc}/{t.slug}"
        # Translation yoksa EN sayfaya yönlendir
        return f"/{page.slug}"

    ctx = common_ctx(request, lang, db=db)
    ctx["lang_urls"] = {lc: _page_lang_url(lc) for lc in SUPPORTED_LANGS}
    ctx.update({
        "page":             page,
        "trans":            trans,
        "faqs":             faqs,
        "meta_title":       meta_title,
        "meta_description": meta_desc,
        "langs":            SUPPORTED_LANGS,
        # Query string olmadan temiz canonical URL
        "canonical_url":    f"https://henib2b.com{request.url.path}",
    })
    template_name = page.template or "page_generic.html"

    # Landing page şablonu için ek context: dile özgü içerik ve paylaşılan görseller
    if template_name == "page_landing.html":
        ctx["data"]   = trans.get_content() if trans else {}
        ctx["shared"] = page.get_shared()

    return templates.TemplateResponse(template_name, ctx)
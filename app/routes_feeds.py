"""
routes_feeds.py
Google Merchant Center XML feed endpoint'leri.
Her desteklenen dil için ayrı bir /merchant.xml URL'si sunar.
"""
import html

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from .database import get_db
from .models import Product
from .services.currency_service import LANG_CURRENCY, convert, get_rates

router = APIRouter()

# Türkçe kategori adı → İngilizce etiket (Google Merchant product_type)
_CATEGORY_EN = {
    "Cilt Bakım":           "Skin Care",
    "Saç Bakım":            "Hair Care",
    "Kişisel Bakım":        "Personal Care",
    "Makyaj":               "Makeup",
    "Parfüm":               "Perfume",
    "Ortam Kokuları":       "Room Fragrances",
    "Genel Temizlik":       "General Cleaning",
    "Çamaşır Yıkama":       "Laundry",
    "Bulaşık Yıkama":       "Dishwashing",
    "Temizlik Malzemeleri": "Cleaning Supplies",
    "Ambalaj":              "Packaging",
    "Kozmetik Hammadde":    "Cosmetic Raw Material",
    "Temizlik Hammadde":    "Cleaning Raw Material",
}

# Dil → ürün detay sayfası URL prefix
_PRODUCT_URL_PREFIX = {
    "en": "/product",
    "tr": "/tr/urun",
    "de": "/de/produkt",
    "fr": "/fr/produit",
    "ar": "/ar/muntaj",
    "ru": "/ru/produkt",
    "es": "/es/producto",
}

# Feed kanal başlıkları
_FEED_TITLE = {
    "en": "HENI - Beauty &amp; Cleaning Products",
    "tr": "HENI - Güzellik ve Temizlik Ürünleri",
    "de": "HENI - Schönheits- und Reinigungsprodukte",
    "fr": "HENI - Produits de Beauté et d'Entretien",
    "ar": "HENI - منتجات التجميل والتنظيف",
    "ru": "HENI - Косметические и чистящие средства",
    "es": "HENI - Productos de Belleza y Limpieza",
}


def _x(text) -> str:
    """XML özel karakterlerini escape eder."""
    if not text:
        return ""
    return html.escape(str(text), quote=False)


def _build_feed(lang: str, base_url: str, products, rates: dict) -> str:
    """Verilen dil ve ürün listesinden Google Merchant Center RSS 2.0 XML üretir."""
    currency       = LANG_CURRENCY.get(lang, "USD")
    product_prefix = _PRODUCT_URL_PREFIX.get(lang, "/product")
    feed_title     = _FEED_TITLE.get(lang, "HENI")

    item_blocks = []
    for product in products:
        # Dile ait çeviriyi bul, yoksa EN'e düş
        translation = next(
            (t for t in product.translations if t.lang == lang), None
        ) or next(
            (t for t in product.translations if t.lang == "en"), None
        )
        if not translation:
            continue

        # Google Merchant'ta görsel zorunlu alan
        if not product.image:
            continue

        # Slug: dile özgü varsa onu, yoksa master slug
        slug = translation.slug or product.slug
        if not slug:
            continue

        # Fiyat zorunlu alan
        if not product.unit_price:
            continue

        price_value, _ = convert(float(product.unit_price), currency, rates)

        # Stok durumu
        availability = "in_stock" if (product.stock or 0) > 0 else "out_of_stock"

        # Açıklama: kısa → uzun → isim önceliğiyle
        description = translation.short_description or ""
        if not description and translation.long_description:
            description = translation.long_description[:5000]
        if not description:
            description = translation.name

        # Kategori İngilizce etiketini bul
        category = _CATEGORY_EN.get(product.category or "", product.category or "")

        # Görsel tam URL (göreceli path ise base URL ekle)
        img_url = product.image
        if img_url and not img_url.startswith("http"):
            img_url = f"{base_url}{img_url}"

        item_blocks.append(
            f"    <item>\n"
            f"      <g:id>{product.id}-{lang}</g:id>\n"
            f"      <g:title>{_x(translation.name)}</g:title>\n"
            f"      <g:description>{_x(description)}</g:description>\n"
            f"      <g:link>{base_url}{product_prefix}/{_x(slug)}</g:link>\n"
            f"      <g:image_link>{_x(img_url)}</g:image_link>\n"
            f"      <g:availability>{availability}</g:availability>\n"
            f"      <g:price>{price_value:.2f} {currency}</g:price>\n"
            f"      <g:condition>new</g:condition>\n"
            f"      <g:brand>HENI</g:brand>\n"
            f"      <g:product_type>{_x(category)}</g:product_type>\n"
            f"      <g:identifier_exists>no</g:identifier_exists>\n"
            f"    </item>"
        )

    items_xml = "\n".join(item_blocks)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n'
        '  <channel>\n'
        f'    <title>{feed_title}</title>\n'
        f'    <link>{base_url}</link>\n'
        '    <description>B2B Beauty and Cleaning Products Wholesale</description>\n'
        f'{items_xml}\n'
        '  </channel>\n'
        '</rss>'
    )


async def _feed_response(lang: str, request: Request, db: Session) -> Response:
    """Verilen dil için XML feed'i üretip HTTP yanıtı olarak döner."""
    products = (
        db.query(Product)
        .options(joinedload(Product.translations))
        .all()
    )
    rates    = get_rates()
    base_url = str(request.base_url).rstrip("/")
    xml      = _build_feed(lang, base_url, products, rates)

    return Response(
        content=xml,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/merchant.xml", include_in_schema=False)
async def feed_en(request: Request, db: Session = Depends(get_db)):
    return await _feed_response("en", request, db)


@router.get("/tr/merchant.xml", include_in_schema=False)
async def feed_tr(request: Request, db: Session = Depends(get_db)):
    return await _feed_response("tr", request, db)


@router.get("/de/merchant.xml", include_in_schema=False)
async def feed_de(request: Request, db: Session = Depends(get_db)):
    return await _feed_response("de", request, db)


@router.get("/fr/merchant.xml", include_in_schema=False)
async def feed_fr(request: Request, db: Session = Depends(get_db)):
    return await _feed_response("fr", request, db)


@router.get("/ar/merchant.xml", include_in_schema=False)
async def feed_ar(request: Request, db: Session = Depends(get_db)):
    return await _feed_response("ar", request, db)


@router.get("/ru/merchant.xml", include_in_schema=False)
async def feed_ru(request: Request, db: Session = Depends(get_db)):
    return await _feed_response("ru", request, db)


@router.get("/es/merchant.xml", include_in_schema=False)
async def feed_es(request: Request, db: Session = Depends(get_db)):
    return await _feed_response("es", request, db)

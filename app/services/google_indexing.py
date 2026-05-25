import json
import os
import logging
import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# uvicorn.error logger'ı Docker'da her zaman stdout'a yazar
logger = logging.getLogger("uvicorn.error")

INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
BASE_URL = "https://henib2b.com"

# routes_showroom.py'deki @router.get tanımlarından türetilmiş URL kalıpları
PRODUCT_URL_MAP = {
    "en": "/product/",
    "tr": "/tr/urun/",
    "de": "/de/produkt/",
    "fr": "/fr/produit/",
    "ar": "/ar/muntaj/",
    "ru": "/ru/produkt/",
    "es": "/es/producto/",
}

CATEGORY_URL_MAP = {
    "en": "/category/",
    "tr": "/tr/kategori/",
    "de": "/de/kategorie/",
    "fr": "/fr/categorie/",
    "ar": "/ar/category/",
    "ru": "/ru/kategoriya/",
    "es": "/es/categoria/",
}

# EN için prefix yok (doğrudan /{slug}), diğerleri /{lang}/{slug}
PAGE_URL_MAP = {
    "en": "/",
    "tr": "/tr/",
    "de": "/de/",
    "fr": "/fr/",
    "ar": "/ar/",
    "ru": "/ru/",
    "es": "/es/",
}


def build_product_urls(translations) -> list:
    """Ürün çevirilerinden tüm dil URL'lerini üretir."""
    return [
        f"{BASE_URL}{PRODUCT_URL_MAP[t.lang]}{t.slug}"
        for t in translations
        if t.slug and t.lang in PRODUCT_URL_MAP
    ]


def build_category_urls(cat_slug: str) -> list:
    """Kategori için tüm dil URL'lerini üretir."""
    return [f"{BASE_URL}{prefix}{cat_slug}" for prefix in CATEGORY_URL_MAP.values()]


def build_page_url(lang: str, slug: str) -> str:
    """CMS sayfa URL'sini doğru prefix ile üretir."""
    prefix = PAGE_URL_MAP.get(lang, f"/{lang}/")
    return f"{BASE_URL}{prefix}{slug}"


def _get_credentials():
    raw = os.environ.get("GOOGLE_OAUTH_TOKEN")
    if not raw:
        raise RuntimeError("GOOGLE_OAUTH_TOKEN environment variable eksik!")
    data = json.loads(raw)
    creds = Credentials(
        token=None,  # her zaman refresh yap
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data["scopes"]
    )
    creds.refresh(Request())
    return creds


def run_notify_google(url: str, action: str = "URL_UPDATED"):
    """BackgroundTasks için sync wrapper — yeni event loop açar."""
    import asyncio
    logger.info(f"Google indexing task başlatıldı: {url}")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(notify_google(url, action))
    except Exception as e:
        logger.error(f"Google indexing wrapper HATA: {url} — {e}")
    finally:
        loop.close()


async def notify_google(url: str, action: str = "URL_UPDATED"):
    try:
        creds = _get_credentials()
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json"
        }
        payload = {"url": url, "type": action}
        async with httpx.AsyncClient() as client:
            response = await client.post(INDEXING_ENDPOINT, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Google indexing OK: {url}")
    except Exception as e:
        logger.error(f"Google indexing FAILED: {url} — {e}")

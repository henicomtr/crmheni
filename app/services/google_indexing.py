import json
import os
import logging
import asyncio
import datetime
import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# uvicorn.error logger'ı Docker'da her zaman stdout'a yazar
logger = logging.getLogger("uvicorn.error")

INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
METADATA_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications/metadata"
BASE_URL = "https://henib2b.com"

# Günlük kota limiti (Google varsayılanı 200/gün, 20 burst/dakika)
DAILY_QUOTA = 200
BURST_QUOTA = 20

# Basit in-memory kota sayacı — sunucu yeniden başlatılınca sıfırlanır
_quota_state: dict = {"date": None, "count": 0}

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


def _check_quota() -> bool:
    """Günlük kota kontrolü — limitdeyse False döner, loglar."""
    today = datetime.date.today().isoformat()
    if _quota_state["date"] != today:
        _quota_state["date"] = today
        _quota_state["count"] = 0
    if _quota_state["count"] >= DAILY_QUOTA:
        logger.warning(
            f"[Indexing API] Günlük kota doldu ({DAILY_QUOTA} istek). "
            f"Yarın otomatik sıfırlanır."
        )
        return False
    _quota_state["count"] += 1
    logger.info(
        f"[Indexing API] Kota: {_quota_state['count']}/{DAILY_QUOTA} "
        f"(bugün gönderildi)"
    )
    return True


def _get_credentials():
    """GOOGLE_OAUTH_TOKEN ortam değişkeninden OAuth kimlik bilgilerini yükler."""
    raw = os.environ.get("GOOGLE_OAUTH_TOKEN")
    if not raw:
        raise RuntimeError(
            "GOOGLE_OAUTH_TOKEN ortam değişkeni eksik! "
            ".env veya sunucu ortamında tanımlanmış olmalı."
        )
    data = json.loads(raw)

    # Gerekli scope kontrolü
    scopes = data.get("scopes", [])
    indexing_scope = "https://www.googleapis.com/auth/indexing"
    if indexing_scope not in scopes:
        logger.warning(
            f"[Indexing API] UYARI: '{indexing_scope}' scope eksik! "
            f"Mevcut scope'lar: {scopes}"
        )

    creds = Credentials(
        token=None,  # her zaman yeni token al
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=scopes,
    )
    creds.refresh(Request())
    logger.debug(f"[Indexing API] Token yenilendi, geçerlilik: {creds.expiry}")
    return creds


def run_notify_google(url: str, action: str = "URL_UPDATED"):
    """BackgroundTasks için sync wrapper."""
    logger.info(f"[Indexing API] Görev başlatıldı: {action} → {url}")
    if not _check_quota():
        return
    try:
        asyncio.run(notify_google(url, action))
    except RuntimeError:
        # Zaten çalışan bir event loop varsa yeni thread açar
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(notify_google(url, action))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"[Indexing API] Wrapper HATA: {url} — {type(e).__name__}: {e}")


async def notify_google(url: str, action: str = "URL_UPDATED"):
    """Google Indexing API'ye URL bildirim isteği gönderir."""
    try:
        creds = _get_credentials()
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        }
        payload = {"url": url, "type": action}

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                INDEXING_ENDPOINT, json=payload, headers=headers
            )

            # Tam yanıt logu — başarısız isteklerde de içeriği görmek için
            try:
                resp_body = response.json()
            except Exception:
                resp_body = response.text

            if response.status_code == 200:
                notify_time = (
                    resp_body.get("urlNotificationMetadata", {})
                    .get("latestUpdate", {})
                    .get("notifyTime", "?")
                )
                logger.info(
                    f"[Indexing API] BAŞARILI ({response.status_code}): {url} "
                    f"| notifyTime: {notify_time}"
                )
            elif response.status_code == 429:
                logger.warning(
                    f"[Indexing API] KOTA AŞILDI (429): {url} "
                    f"| Yanıt: {resp_body}"
                )
            elif response.status_code in (401, 403):
                logger.error(
                    f"[Indexing API] YETKİ HATASI ({response.status_code}): {url} "
                    f"| Yanıt: {resp_body} "
                    f"| Search Console'da OAuth hesabı verified owner olarak eklenmiş mi?"
                )
            else:
                logger.error(
                    f"[Indexing API] HATA ({response.status_code}): {url} "
                    f"| Yanıt: {resp_body}"
                )

            response.raise_for_status()

    except httpx.HTTPStatusError as e:
        logger.error(
            f"[Indexing API] HTTP HATA: {url} — {e.response.status_code}: {e}"
        )
    except Exception as e:
        logger.error(
            f"[Indexing API] GENEL HATA: {url} — {type(e).__name__}: {e}"
        )

import json
import os
import logging
import asyncio
import datetime
import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from sqlalchemy.orm import Session

logger = logging.getLogger("uvicorn.error")

INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
BASE_URL = "https://henib2b.com"

# Günlük kota limiti (Google varsayılanı 200/gün)
DAILY_QUOTA = 200

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


def queue_url(db: Session, url: str, action: str = "URL_UPDATED") -> None:
    """URL'yi indexing kuyruğuna ekler; aynı URL zaten pending ise atlar."""
    from app.models import IndexingQueue
    mevcut = (
        db.query(IndexingQueue)
        .filter(IndexingQueue.url == url, IndexingQueue.status == "pending")
        .first()
    )
    if mevcut:
        logger.debug(f"[IndexingQueue] Zaten kuyrukta: {url}")
        return
    db.add(IndexingQueue(url=url, action=action))
    db.commit()
    logger.info(f"[IndexingQueue] Kuyruğa eklendi: {url}")


def get_queue_stats(db: Session) -> dict:
    """Kuyruk durumunu özet olarak döner."""
    from app.models import IndexingQueue
    from sqlalchemy import func
    rows = (
        db.query(IndexingQueue.status, func.count(IndexingQueue.id))
        .group_by(IndexingQueue.status)
        .all()
    )
    stats = {status: count for status, count in rows}
    return {
        "pending": stats.get("pending", 0),
        "sent":    stats.get("sent", 0),
        "failed":  stats.get("failed", 0),
    }


def _get_credentials():
    """GOOGLE_OAUTH_TOKEN ortam değişkeninden OAuth kimlik bilgilerini yükler."""
    raw = os.environ.get("GOOGLE_OAUTH_TOKEN")
    if not raw:
        raise RuntimeError(
            "GOOGLE_OAUTH_TOKEN ortam değişkeni eksik! "
            ".env veya sunucu ortamında tanımlanmış olmalı."
        )
    data = json.loads(raw)

    scopes = data.get("scopes", [])
    indexing_scope = "https://www.googleapis.com/auth/indexing"
    if indexing_scope not in scopes:
        logger.warning(
            f"[Indexing API] UYARI: '{indexing_scope}' scope eksik! "
            f"Mevcut scope'lar: {scopes}"
        )

    creds = Credentials(
        token=None,
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=scopes,
    )
    creds.refresh(Request())
    return creds


async def _send_one(client: httpx.AsyncClient, headers: dict, url: str, action: str) -> dict:
    """Tek URL için API isteği atar; sonucu dict olarak döner."""
    payload = {"url": url, "type": action}
    try:
        response = await client.post(INDEXING_ENDPOINT, json=payload, headers=headers)
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
            logger.info(f"[Indexing API] OK ({response.status_code}): {url} | notifyTime: {notify_time}")
            return {"ok": True, "error": None}
        elif response.status_code == 429:
            msg = f"Kota aşıldı (429): {resp_body}"
            logger.warning(f"[Indexing API] {msg} — {url}")
            return {"ok": False, "error": msg}
        elif response.status_code in (401, 403):
            msg = (
                f"Yetki hatası ({response.status_code}): {resp_body} — "
                "Search Console'da OAuth hesabı Verified Owner olarak eklenmiş mi?"
            )
            logger.error(f"[Indexing API] {msg} — {url}")
            return {"ok": False, "error": msg}
        else:
            msg = f"HTTP {response.status_code}: {resp_body}"
            logger.error(f"[Indexing API] HATA: {url} — {msg}")
            return {"ok": False, "error": msg}
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        logger.error(f"[Indexing API] İSTEK HATASI: {url} — {msg}")
        return {"ok": False, "error": msg}


async def _send_all_async(db: Session) -> dict:
    """Kuyrukta bekleyen tüm pending URL'leri gönderir."""
    from app.models import IndexingQueue

    pending = (
        db.query(IndexingQueue)
        .filter(IndexingQueue.status == "pending")
        .order_by(IndexingQueue.created_at)
        .all()
    )

    if not pending:
        return {"sent": 0, "failed": 0, "skipped": 0, "message": "Kuyrukta gönderilecek URL yok."}

    if len(pending) > DAILY_QUOTA:
        logger.warning(
            f"[Indexing API] Kuyrukta {len(pending)} URL var, günlük kota {DAILY_QUOTA}. "
            f"İlk {DAILY_QUOTA} gönderilecek."
        )

    try:
        creds = _get_credentials()
    except Exception as e:
        logger.error(f"[Indexing API] Kimlik bilgisi alınamadı: {e}")
        return {"sent": 0, "failed": 0, "skipped": len(pending), "message": str(e)}

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }

    sent = 0
    failed = 0
    skipped = max(0, len(pending) - DAILY_QUOTA)
    batch = pending[:DAILY_QUOTA]

    async with httpx.AsyncClient(timeout=15.0) as client:
        for item in batch:
            result = await _send_one(client, headers, item.url, item.action)
            now = datetime.datetime.utcnow()
            if result["ok"]:
                item.status = "sent"
                item.sent_at = now
                item.error_msg = None
                sent += 1
            else:
                item.status = "failed"
                item.sent_at = now
                item.error_msg = result["error"]
                failed += 1
            db.commit()

    return {
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "message": (
            f"{sent} URL gönderildi, {failed} hata, {skipped} kota nedeniyle atlandı."
        ),
    }


def send_all_pending(db: Session) -> dict:
    """Sync wrapper — admin route'larından çağrılır."""
    try:
        return asyncio.run(_send_all_async(db))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_send_all_async(db))
        finally:
            loop.close()

# -*- coding: utf-8 -*-
"""
Push Notification endpoint'leri (Web Push / VAPID).

ENV değişkenleri:
  VAPID_PRIVATE_KEY  — PEM formatında private key (newline'lar \\n ile)
  VAPID_PUBLIC_KEY   — URL-safe base64 public key
  VAPID_CLAIMS_EMAIL — mailto: adresi (örn. admin@henib2b.com)

Abonelikler bellek içinde tutulur (uygulama yeniden başlayınca sıfırlanır).
Kalıcı depolama için ileride DB'ye taşıyabilirsiniz.
"""

import os
import json
import logging
from typing import List

from fastapi import APIRouter, Request, Depends, Cookie
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
from pywebpush import webpush, WebPushException

from .config import SECRET_KEY, ALGORITHM
from .database import get_db
from .models import User
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter()

# ── VAPID ayarları ─────────────────────────────────────────────────────────────
# VAPID_PRIVATE_KEY: raw base64url formatında 43 karakterlik EC private key.
# Örnek: zD8GuyIvvSEWMj2-ne9VrZU0-L6Jqlr-qrRT0eTy2qU
# PEM veya \n içeren değerleri de temizleyerek py_vapid'e uygun hale getirir.
VAPID_PUBLIC_KEY    = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS_EMAIL  = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:admin@henib2b.com")

def _normalize_vapid_private_key(raw: str) -> str:
    """
    VAPID private key'i py_vapid'in from_string() metoduna uygun hale getirir.
    py_vapid 2.x yalnızca raw base64url (43 char) kabul eder; PEM kabul etmez.
    PEM formatındaysa içindeki 32-byte private key scalar'ı çıkarıp base64url döner.
    """
    if not raw:
        return ""
    key = raw.replace("\\n", "\n").strip()
    if "BEGIN PRIVATE KEY" not in key:
        # Zaten raw base64url — olduğu gibi kullan
        return key
    # PEM'den raw 32-byte scalar'ı çıkar
    try:
        import base64 as _b64
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        priv = load_pem_private_key(key.encode(), password=None)
        raw_int = priv.private_numbers().private_value
        raw_bytes = raw_int.to_bytes(32, "big")
        return _b64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode()
    except Exception as exc:
        logger.error("[push] VAPID PEM → raw dönüşüm hatası: %s", exc)
        return key

VAPID_PRIVATE_KEY = _normalize_vapid_private_key(os.getenv("VAPID_PRIVATE_KEY", "").strip())

# ── Abonelik deposu (bellek) ───────────────────────────────────────────────────
# { endpoint_url: subscription_dict }
_subscriptions: dict = {}


def _admin_required(token: str = Cookie(None), db: Session = Depends(get_db)):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            return None
        return db.query(User).filter(User.email == email).first()
    except JWTError:
        return None


# ── Public key endpoint ────────────────────────────────────────────────────────
@router.get("/esk/push/vapid-public-key")
def vapid_public_key():
    """Frontend'in abone olurken kullandığı public key."""
    return JSONResponse({"publicKey": VAPID_PUBLIC_KEY})


# ── Abone ol ──────────────────────────────────────────────────────────────────
@router.post("/esk/push/subscribe")
async def push_subscribe(request: Request, admin=Depends(_admin_required)):
    if not admin:
        return JSONResponse({"error": "Yetkisiz"}, status_code=401)

    body = await request.json()
    endpoint = body.get("endpoint")
    if not endpoint:
        return JSONResponse({"error": "Geçersiz abonelik"}, status_code=400)

    _subscriptions[endpoint] = body
    logger.info(f"[push] Yeni abonelik kaydedildi: {endpoint[:60]}… (toplam: {len(_subscriptions)})")
    return JSONResponse({"ok": True})


# ── Abonelikten çık ───────────────────────────────────────────────────────────
@router.post("/esk/push/unsubscribe")
async def push_unsubscribe(request: Request, admin=Depends(_admin_required)):
    if not admin:
        return JSONResponse({"error": "Yetkisiz"}, status_code=401)

    body = await request.json()
    endpoint = body.get("endpoint")
    if endpoint and endpoint in _subscriptions:
        del _subscriptions[endpoint]
        logger.info(f"[push] Abonelik silindi: {endpoint[:60]}…")
    return JSONResponse({"ok": True})


# ── Push gönder (iç kullanım) ─────────────────────────────────────────────────
def send_push_notification(title: str, body: str, url: str = "/esk/requests", db=None):
    """
    Kayıtlı tüm abonelere push bildirim gönderir.
    routes_admin.py / routes_showroom.py içinden import edilerek çağrılır.
    db verilirse okunmamış talep sayısını badge olarak iletir.
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.warning("[push] VAPID key'ler ayarlanmamış, bildirim atlandı.")
        return

    if not _subscriptions:
        return

    # Okunmamış talep sayısını badge için hesapla
    count = 0
    if db is not None:
        try:
            from .models import QuoteRequest
            count = db.query(QuoteRequest).filter(QuoteRequest.is_read == False).count()
        except Exception:
            pass

    payload = json.dumps({
        "title": title,
        "body":  body,
        "url":   url,
        "count": count,
    })

    dead: List[str] = []
    for endpoint, sub in list(_subscriptions.items()):
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
                ttl=86400,                          # FCM 24 saat kuyruğa al
                headers={"Urgency": "high"},        # Anında ilet
            )
            logger.info(f"[push] Gönderildi → {endpoint[:60]}…")
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            detail = ""
            try:
                detail = e.response.text[:200] if e.response else ""
            except Exception:
                pass
            logger.warning(f"[push] Gönderilemedi HTTP {status}: {endpoint[:60]}… | {detail}")
            # 404/410 → abonelik geçersiz, sil
            if status in (404, 410):
                dead.append(endpoint)
        except Exception as e:
            logger.warning(f"[push] Beklenmeyen hata: {e}")

    for ep in dead:
        _subscriptions.pop(ep, None)
        logger.info(f"[push] Geçersiz abonelik temizlendi: {ep[:60]}…")


# ── Service Worker'ı root path'den serve et ───────────────────────────────────
# SW dosyası /static/ altında olursa scope /static/ ile sınırlı kalır.
# /sw.js route'u ile root scope'ta çalışmasını sağlıyoruz.
@router.get("/sw.js")
def serve_sw():
    import os
    from fastapi.responses import FileResponse
    sw_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "sw.js"
    )
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


# ── Push kurulum durumu (hata ayıklama) ───────────────────────────────────────
@router.get("/esk/push/debug")
def push_debug(admin=Depends(_admin_required)):
    """Push bildirim kurulum durumunu döner (tarayıcıdan kontrol için)."""
    if not admin:
        return JSONResponse({"error": "Yetkisiz"}, status_code=401)
    return JSONResponse({
        "vapid_configured": bool(VAPID_PRIVATE_KEY.strip() and VAPID_PUBLIC_KEY),
        "subscriber_count": len(_subscriptions),
        "public_key_prefix": VAPID_PUBLIC_KEY[:20] + "..." if VAPID_PUBLIC_KEY else "",
    })


# ── Manuel test endpoint'i ─────────────────────────────────────────────────────
@router.post("/esk/push/test")
def push_test(admin=Depends(_admin_required), db: Session = Depends(get_db)):
    """Admin panelinden push bildirimini test etmek için."""
    if not admin:
        return JSONResponse({"error": "Yetkisiz"}, status_code=401)
    send_push_notification(
        title="🔔 Test Bildirimi",
        body="Push bildirimler çalışıyor!",
        url="/esk/requests",
        db=db,
    )
    return JSONResponse({"ok": True, "subscribers": len(_subscriptions)})


# ── Ayrıntılı push testi — her aboneye HTTP sonucunu döner ────────────────────
@router.post("/esk/push/test-verbose")
def push_test_verbose(admin=Depends(_admin_required)):
    """Her abonenin push gönderim sonucunu (ok/hata + HTTP kodu) döner."""
    if not admin:
        return JSONResponse({"error": "Yetkisiz"}, status_code=401)
    if not VAPID_PRIVATE_KEY.strip() or not VAPID_PUBLIC_KEY:
        return JSONResponse({"error": "VAPID key yapılandırılmamış"})
    if not _subscriptions:
        return JSONResponse({"error": "Kayıtlı abone yok"})

    results = []
    payload = json.dumps({
        "title": "🔔 Verbose Test",
        "body":  "Push ayrıntılı test mesajı.",
        "url":   "/esk/requests",
        "count": 0,
    })

    for endpoint, sub in list(_subscriptions.items()):
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
                ttl=86400,
                headers={"Urgency": "high"},
            )
            results.append({"endpoint": endpoint[:70] + "...", "ok": True, "http_status": 201})
        except WebPushException as e:
            http_status = getattr(e.response, "status_code", None)
            detail = ""
            try:
                detail = e.response.text[:300] if e.response else str(e)[:300]
            except Exception:
                detail = str(e)[:300]
            results.append({"endpoint": endpoint[:70] + "...", "ok": False,
                            "http_status": http_status, "detail": detail})
        except Exception as e:
            results.append({"endpoint": endpoint[:70] + "...", "ok": False,
                            "detail": str(e)[:300]})

    return JSONResponse({"results": results, "total": len(results)})

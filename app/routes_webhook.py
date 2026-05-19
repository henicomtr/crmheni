"""
Webhook endpoint'leri:
  - POST /webhook/evolution  → Evolution API'den gelen WhatsApp mesajlarını yakalar
  - GET  /webhook/imap-poll  → Manuel IMAP polling tetikleyici (test için)

IMAP polling, uygulama başlangıcında arka plan görevi olarak başlatılır.
"""

import re
import base64
import imaplib
import email as email_lib
import email.header
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .database import get_db, SessionLocal
from .models import QuoteRequest, RequestMessage, SiteSettings

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """Telefon numarasından tüm harf dışı karakterleri silerek sadece rakamları döner."""
    return re.sub(r"\D", "", phone or "")


def _phones_match(phone_a: str, phone_b: str) -> bool:
    """
    İki telefon numarasını karşılaştırır.
    Ülke kodu farkını tolere etmek için sondan 9 rakam eşleşmesi yeterlidir.
    """
    a = _normalize_phone(phone_a)
    b = _normalize_phone(phone_b)
    if not a or not b:
        return False
    return a[-9:] == b[-9:]


def _decode_if_base64(value: str) -> str:
    """
    Değer base64 ise decode eder, değilse olduğu gibi döner.
    webhookBase64:true modunda Evolution API metin alanlarını base64'e çevirir.
    """
    if not value or not isinstance(value, str):
        return value
    try:
        decoded = base64.b64decode(value).decode("utf-8")
        # Sadece printable karakter içeriyorsa gerçek base64 sayılır
        if decoded.isprintable() or "\n" in decoded:
            return decoded
    except Exception:
        pass
    return value


def _extract_wa_text(message_data: dict) -> Optional[str]:
    """Evolution API mesaj objesinden metin içeriğini çıkarır (base64 destekli)."""
    msg = message_data.get("message") or {}
    # Düz metin
    if "conversation" in msg:
        return _decode_if_base64(msg["conversation"])
    # Genişletilmiş metin
    if "extendedTextMessage" in msg:
        text = msg["extendedTextMessage"].get("text", "")
        return _decode_if_base64(text)
    # Görsel + caption
    for key in ("imageMessage", "videoMessage", "documentMessage"):
        if key in msg and msg[key].get("caption"):
            caption = _decode_if_base64(msg[key]["caption"])
            return f"[{key.replace('Message', '').capitalize()}] {caption}"
    # Sadece medya, metin yok
    for key in ("imageMessage", "videoMessage", "audioMessage", "stickerMessage"):
        if key in msg:
            return f"[{key.replace('Message', '').capitalize()} mesajı]"
    return None


def _find_request_by_phone(db: Session, phone: str) -> Optional[QuoteRequest]:
    """Telefon numarasına göre en son QuoteRequest'i bulur."""
    normalized_incoming = _normalize_phone(phone)
    all_requests = db.query(QuoteRequest).filter(QuoteRequest.phone.isnot(None)).all()
    logger.info(
        "Telefon eşleştirme: aranan=%s (normalize=%s), %d talep kontrol edilecek",
        phone, normalized_incoming, len(all_requests)
    )
    for req in all_requests:
        normalized_stored = _normalize_phone(req.phone)
        if _phones_match(req.phone, phone):
            logger.info("Eşleşme bulundu → Talep #%d, kayıtlı telefon=%s (normalize=%s)",
                        req.id, req.phone, normalized_stored)
            return req
    logger.warning(
        "Eşleşme yok: aranan=%s → kayıtlı telefonlar: %s",
        normalized_incoming,
        [_normalize_phone(r.phone) for r in all_requests[:10]]  # İlk 10 tanesini logla
    )
    return None


def _save_incoming_message(db: Session, request_id: int, channel: str, content: str, sender: Optional[str] = None):
    """Gelen müşteri mesajını veritabanına kaydeder."""
    msg = RequestMessage(
        request_id=request_id,
        channel=channel,
        direction="incoming",
        content=content,
        admin_name=sender,
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    # Son iletişim tarihini güncelle
    req = db.query(QuoteRequest).filter(QuoteRequest.id == request_id).first()
    if req:
        req.last_contacted_at = datetime.utcnow()
        req.is_read = False  # Yeni mesaj geldi, okunmadı olarak işaretle
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Evolution API Webhook
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/webhook/evolution")
async def evolution_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Evolution API'nin gönderdiği gelen WhatsApp mesajlarını yakalar.
    Gönderenin telefonu ile quote_requests.phone eşleştirilir.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.error("Evolution webhook: geçersiz JSON")
        return {"status": "invalid_json"}

    event = payload.get("event", "")
    # Tüm gelen webhook çağrılarını logla (teşhis için)
    logger.warning("Evolution webhook alındı → event=%r, payload_keys=%s", event, list(payload.keys()))

    # Evolution API v2: MESSAGES_UPSERT (büyük harf) veya messages.upsert (küçük) gönderebilir
    _ACCEPTED_EVENTS = {"messages.upsert", "message.upsert", "MESSAGES_UPSERT", "MESSAGE_UPSERT"}
    if event not in _ACCEPTED_EVENTS:
        logger.warning("Evolution webhook yoksayıldı → event=%r", event)
        return {"status": "ignored", "event": event}

    # Payload bazen data listesi, bazen tekil obje olarak gelir
    data_raw = payload.get("data", {})
    messages_list = data_raw if isinstance(data_raw, list) else [data_raw]

    logger.info("Evolution webhook: %d mesaj işlenecek", len(messages_list))

    processed = 0
    for msg_data in messages_list:
        key = msg_data.get("key", {})

        # Kendi gönderdiğimiz mesajları atla
        if key.get("fromMe", False):
            logger.info("fromMe=true mesaj atlandı")
            continue

        remote_jid = key.get("remoteJid", "")
        logger.info("Gelen mesaj: remoteJid=%s, pushName=%s", remote_jid, msg_data.get("pushName"))

        # Grup mesajlarını atla (@g.us ile biten JID'ler)
        if "@g.us" in remote_jid:
            logger.info("Grup mesajı atlandı: %s", remote_jid)
            continue

        # Telefon numarasını JID'den çıkar: "905551234567@s.whatsapp.net" → "905551234567"
        sender_phone = remote_jid.split("@")[0]
        sender_name  = msg_data.get("pushName", None)

        text_content = _extract_wa_text(msg_data)
        logger.info("Metin içerik: phone=%s, content=%r", sender_phone, text_content)

        if not text_content:
            logger.info("Metin içerik yok, mesaj atlandı (phone=%s)", sender_phone)
            continue

        # Telefon numarasıyla talep bul
        quote_req = _find_request_by_phone(db, sender_phone)
        if not quote_req:
            logger.warning("Eşleşen talep bulunamadı, telefon: %s", sender_phone)
            continue

        _save_incoming_message(
            db=db,
            request_id=quote_req.id,
            channel="whatsapp",
            content=text_content,
            sender=sender_name or sender_phone,
        )
        processed += 1
        logger.info("WhatsApp mesajı kaydedildi → Talep #%d (gönderen: %s)", quote_req.id, sender_phone)

    return {"status": "ok", "processed": processed}


# ─────────────────────────────────────────────────────────────────────────────
# IMAP Email Polling
# ─────────────────────────────────────────────────────────────────────────────

def _decode_header_value(raw: str) -> str:
    """Email header değerini UTF-8'e çevirir."""
    parts = email.header.decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_request_id_from_subject(subject: str) -> Optional[int]:
    """Subject'ten 'Talep #42' veya 'Teklif #42' formatını parse eder."""
    match = re.search(r"#(\d+)", subject or "")
    if match:
        return int(match.group(1))
    return None


def _get_email_body(msg: email_lib.message.Message) -> str:
    """Email mesajından düz metin body'yi çıkarır."""
    body_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition  = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition:
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_parts.append(part.get_payload(decode=True).decode(charset, errors="replace"))
                except Exception:
                    pass
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            body_parts.append(msg.get_payload(decode=True).decode(charset, errors="replace"))
        except Exception:
            pass
    return "\n".join(body_parts).strip()


def _poll_imap_once():
    """
    IMAP kutusunu bir kez tarar. Okunmamış mailleri işler:
    1. Subject'te Talep #ID varsa o talebe bağlar.
    2. Yoksa gönderen email'i quote_requests.email ile eşleştirir.
    3. Eşleşen mesajı incoming olarak kaydeder, maili okundu işaretler.
    """
    db = SessionLocal()
    try:
        settings = db.query(SiteSettings).first()
        if not settings:
            return

        # IMAP ayarları kontrol et
        imap_host = settings.imap_host
        imap_port = settings.imap_port or 993
        imap_user = settings.imap_user or settings.smtp_user
        imap_pass = settings.imap_password or settings.smtp_password

        if not all([imap_host, imap_user, imap_pass]):
            return  # IMAP henüz yapılandırılmamış

        # IMAP bağlantısı
        try:
            mail = imaplib.IMAP4_SSL(imap_host, imap_port)
            mail.login(imap_user, imap_pass)
        except Exception as exc:
            logger.error("IMAP bağlantı hatası: %s", exc)
            return

        try:
            mail.select("INBOX")
            # Sadece okunmamış mailleri al
            _, msg_ids = mail.search(None, "UNSEEN")
            if not msg_ids or not msg_ids[0]:
                return

            for msg_id in msg_ids[0].split():
                try:
                    _, msg_data = mail.fetch(msg_id, "(RFC822)")
                    raw_email = msg_data[0][1]
                    parsed    = email_lib.message_from_bytes(raw_email)

                    subject    = _decode_header_value(parsed.get("Subject", ""))
                    from_field = _decode_header_value(parsed.get("From", ""))
                    body       = _get_email_body(parsed)

                    if not body:
                        continue

                    # Gönderen adresi çıkar: "Ad Soyad <mail@ornek.com>" → "mail@ornek.com"
                    from_email_match = re.search(r"[\w.\-+]+@[\w.\-]+", from_field)
                    from_email = from_email_match.group(0).lower() if from_email_match else ""

                    # Kendi sunucumuzdan gelen mailleri atla
                    if imap_user and from_email == imap_user.lower():
                        mail.store(msg_id, "+FLAGS", "\\Seen")
                        continue

                    # 1. Subject'ten talep ID'si bul
                    req_id = _extract_request_id_from_subject(subject)
                    quote_req = None
                    if req_id:
                        quote_req = db.query(QuoteRequest).filter(QuoteRequest.id == req_id).first()

                    # 2. Bulunamazsa email eşleştirmesi dene
                    if not quote_req and from_email:
                        quote_req = (
                            db.query(QuoteRequest)
                            .filter(QuoteRequest.email.ilike(from_email))
                            .order_by(QuoteRequest.created_at.desc())
                            .first()
                        )

                    if not quote_req:
                        # Eşleşen talep yok — okunmamış bırak, spam değil
                        logger.info("IMAP: eşleşen talep bulunamadı, gönderen: %s", from_email)
                        continue

                    _save_incoming_message(
                        db=db,
                        request_id=quote_req.id,
                        channel="email",
                        content=f"Konu: {subject}\n\n{body}",
                        sender=from_field or from_email,
                    )
                    # Maili okundu olarak işaretle
                    mail.store(msg_id, "+FLAGS", "\\Seen")
                    logger.info("Email cevabı kaydedildi → Talep #%d", quote_req.id)

                except Exception as exc:
                    logger.error("IMAP mesaj işleme hatası (id=%s): %s", msg_id, exc)

        finally:
            try:
                mail.logout()
            except Exception:
                pass

    finally:
        db.close()


async def _imap_polling_loop():
    """Her 5 dakikada bir IMAP kutusunu tarayan arka plan döngüsü."""
    # İlk çalışmayı 30 saniye geciktir (uygulama tam ayağa kalksın)
    await asyncio.sleep(30)
    while True:
        try:
            _poll_imap_once()
        except Exception as exc:
            logger.error("IMAP polling döngüsü hatası: %s", exc)
        await asyncio.sleep(300)  # 5 dakika


def start_imap_polling(app):
    """FastAPI startup event'inde çağrılır — IMAP polling'i başlatır."""
    loop = asyncio.get_event_loop()
    loop.create_task(_imap_polling_loop())


async def _register_evolution_webhook():
    """
    Evolution API'ye CRM'in webhook URL'sini kaydeder.
    Sunucu her başladığında çağrılır — idempotent (tekrar kayıt sorun yaratmaz).
    crm_base_url ayarı yoksa kayıt atlanır: localhost'ta webhook çalışmaz,
    ngrok gibi bir tünel açıp admin ayarlarından crm_base_url girilmesi gerekir.
    """
    import httpx
    db = SessionLocal()
    try:
        settings = db.query(SiteSettings).first()
        if not settings:
            return

        evo_url  = settings.evolution_api_url
        evo_key  = settings.evolution_api_key
        evo_inst = settings.evolution_instance

        if not all([evo_url, evo_key, evo_inst]):
            logger.warning("Evolution API ayarları eksik, webhook kaydı atlandı.")
            return

        # crm_base_url admin ayarlarından okunur; girilmemişse webhook kaydı yapılamaz
        crm_base = (settings.crm_base_url or "").rstrip("/")
        if not crm_base:
            logger.warning(
                "crm_base_url ayarlanmamış — Evolution webhook kaydı atlandı. "
                "Admin Ayarları → Entegrasyon bölümünden CRM URL'sini girin "
                "(üretim: https://henib2b.com, lokal: ngrok URL'si)."
            )
            return

        # Evolution API bu adrese POST atacak
        webhook_url = f"{crm_base}/webhook/evolution"

        endpoint = f"{evo_url.rstrip('/')}/webhook/set/{evo_inst}"
        # Evolution API v2: camelCase alan adları kullanılmalı
        payload  = {
            "webhook": {
                "url": webhook_url,
                "enabled": True,
                "webhookByEvents": False,
                "webhookBase64": False,
                "events": ["MESSAGES_UPSERT"],
            }
        }
        headers  = {"apikey": evo_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                logger.warning("Evolution webhook kaydedildi: %s → cevap: %s", webhook_url, resp.text[:200])
            else:
                logger.warning("Evolution webhook kayıt başarısız: %d %s", resp.status_code, resp.text)

    except Exception as exc:
        logger.error("Evolution webhook kayıt hatası: %s", exc)
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Manuel tetikleyici ve tanı endpoint'leri
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/webhook/imap-poll")
def trigger_imap_poll(db: Session = Depends(get_db)):
    """Admin'in manuel olarak IMAP polling tetiklemesi için endpoint."""
    try:
        _poll_imap_once()
        return {"status": "ok", "message": "IMAP taraması tamamlandı"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.get("/webhook/evolution-status")
async def get_evolution_webhook_status():
    """Evolution API'de kayıtlı webhook bilgisini döner (tanı için)."""
    import httpx
    db = SessionLocal()
    try:
        settings = db.query(SiteSettings).first()
        if not settings:
            return {"error": "ayarlar bulunamadı"}

        evo_url  = settings.evolution_api_url
        evo_key  = settings.evolution_api_key
        evo_inst = settings.evolution_instance

        if not all([evo_url, evo_key, evo_inst]):
            return {"error": "Evolution API ayarları eksik", "url": evo_url, "instance": evo_inst}

        endpoint = f"{evo_url.rstrip('/')}/webhook/find/{evo_inst}"
        headers  = {"apikey": evo_key}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(endpoint, headers=headers)
            return {
                "http_status": resp.status_code,
                "evolution_url": evo_url,
                "instance": evo_inst,
                "webhook_data": resp.json() if resp.status_code == 200 else resp.text,
            }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        db.close()


@router.get("/webhook/evolution-register")
async def manual_register_evolution_webhook():
    """Evolution API webhook kaydını manuel olarak yeniler (tanı + düzeltme için)."""
    await _register_evolution_webhook()
    return {"status": "ok", "message": "Kayıt isteği gönderildi, Docker loglarını kontrol edin."}


# ─────────────────────────────────────────────────────────────────────────────
# Test endpoint'leri (eskiden var olan, korunuyor)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/webhook/test")
def webhook_test():
    return {"status": "ok"}

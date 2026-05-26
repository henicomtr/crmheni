# -*- coding: utf-8 -*-
"""
Proforma Invoice route'ları.
Prefix: /esk/proformalar
İzin: "proformalar"
"""

from fastapi import APIRouter, Request, Depends, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
import json

from .database import get_db
from .models import ProformaInvoice, ProformaItem, SiteSettings, User
from .config import SECRET_KEY, ALGORITHM
from .services.proforma_service import (
    generate_pdf_bytes,
    send_proforma_email,
    generate_next_pi_number,
)

from jose import jwt, JWTError

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ── Yardımcı: JWT doğrulama ──────────────────────────────────────────

def _get_current_user(request: Request, db: Session) -> Optional[User]:
    """Cookie'den JWT token okur, User nesnesini döner. Geçersizse None."""
    token = request.cookies.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            return None
        return db.query(User).filter(User.email == email).first()
    except JWTError:
        return None


def _require_permission(request: Request, db: Session, perm: str):
    """
    Kullanıcı oturumunu ve iznini kontrol eder.
    Yetkisizse login sayfasına yönlendirir (RedirectResponse döner),
    aksi hâlde User nesnesini döner.
    """
    user = _get_current_user(request, db)
    if not user:
        return RedirectResponse("/esk/login", status_code=302)
    if not user.has_permission(perm):
        return RedirectResponse("/esk/dashboard", status_code=302)
    return user


def _get_settings(db: Session) -> SiteSettings:
    settings = db.query(SiteSettings).first()
    if not settings:
        settings = SiteSettings()
    return settings


# ────────────────────────────────────────────────────────────────────
# LİSTE
# ────────────────────────────────────────────────────────────────────

@router.get("/esk/proformalar", response_class=HTMLResponse)
def list_proformalar(
    request: Request,
    status: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result
    current_user = result

    query = db.query(ProformaInvoice)
    if status:
        query = query.filter(ProformaInvoice.status == status)
    if q:
        query = query.filter(
            ProformaInvoice.pi_number.ilike(f"%{q}%")
            | ProformaInvoice.buyer_company.ilike(f"%{q}%")
            | ProformaInvoice.buyer_email.ilike(f"%{q}%")
        )
    proformalar = query.order_by(ProformaInvoice.id.desc()).all()

    return templates.TemplateResponse("admin_proformalar.html", {
        "request": request,
        "current_user": current_user,
        "proformalar": proformalar,
        "status_filter": status or "",
        "q": q or "",
    })


# ────────────────────────────────────────────────────────────────────
# YENİ PROFORMA — FORM
# ────────────────────────────────────────────────────────────────────

@router.get("/esk/proformalar/yeni", response_class=HTMLResponse)
def new_proforma_form(
    request: Request,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result
    current_user = result

    settings = _get_settings(db)
    next_pi = generate_next_pi_number(db)
    today = datetime.utcnow().strftime("%d.%m.%Y")

    return templates.TemplateResponse("admin_proforma_form.html", {
        "request": request,
        "current_user": current_user,
        "settings": settings,
        "invoice": None,
        "next_pi": next_pi,
        "today": today,
        "mode": "create",
    })


# ────────────────────────────────────────────────────────────────────
# YENİ PROFORMA — KAYDET
# ────────────────────────────────────────────────────────────────────

@router.post("/esk/proformalar/yeni")
async def create_proforma(
    request: Request,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result
    current_user = result

    form = await request.form()
    invoice = _build_invoice_from_form(form, db)
    invoice.created_by = current_user.id
    db.add(invoice)
    db.flush()  # ID ata, items için gerekli

    _save_items_from_form(form, invoice.id, db)
    db.commit()

    return RedirectResponse(f"/esk/proformalar/{invoice.id}", status_code=303)


# ────────────────────────────────────────────────────────────────────
# PROFORMA DETAY / ÖNİZLEME
# ────────────────────────────────────────────────────────────────────

@router.get("/esk/proformalar/{invoice_id}", response_class=HTMLResponse)
def proforma_detail(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result
    current_user = result

    invoice = db.query(ProformaInvoice).filter(ProformaInvoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/esk/proformalar", status_code=302)

    settings = _get_settings(db)

    # Revizyon geçmişi (en yakın üst)
    revision_chain = _build_revision_chain(invoice, db)

    return templates.TemplateResponse("admin_proforma_detail.html", {
        "request": request,
        "current_user": current_user,
        "invoice": invoice,
        "settings": settings,
        "revision_chain": revision_chain,
    })


# ────────────────────────────────────────────────────────────────────
# PROFORMA DÜZENLE — FORM
# ────────────────────────────────────────────────────────────────────

@router.get("/esk/proformalar/{invoice_id}/duzenle", response_class=HTMLResponse)
def edit_proforma_form(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result
    current_user = result

    invoice = db.query(ProformaInvoice).filter(ProformaInvoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/esk/proformalar", status_code=302)

    settings = _get_settings(db)

    return templates.TemplateResponse("admin_proforma_form.html", {
        "request": request,
        "current_user": current_user,
        "settings": settings,
        "invoice": invoice,
        "next_pi": invoice.pi_number,
        "today": invoice.issue_date,
        "mode": "edit",
    })


# ────────────────────────────────────────────────────────────────────
# PROFORMA DÜZENLE — KAYDET
# ────────────────────────────────────────────────────────────────────

@router.post("/esk/proformalar/{invoice_id}/duzenle")
async def update_proforma(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result

    invoice = db.query(ProformaInvoice).filter(ProformaInvoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/esk/proformalar", status_code=302)

    form = await request.form()
    _update_invoice_from_form(invoice, form)

    # Eski kalemleri sil, yenilerini ekle
    db.query(ProformaItem).filter(ProformaItem.invoice_id == invoice_id).delete()
    _save_items_from_form(form, invoice_id, db)

    invoice.updated_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(f"/esk/proformalar/{invoice_id}", status_code=303)


# ────────────────────────────────────────────────────────────────────
# PROFORMA GÖNDER
# ────────────────────────────────────────────────────────────────────

@router.post("/esk/proformalar/{invoice_id}/gonder")
def send_proforma(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result

    invoice = db.query(ProformaInvoice).filter(ProformaInvoice.id == invoice_id).first()
    if not invoice:
        return JSONResponse({"ok": False, "error": "Proforma bulunamadı."}, status_code=404)

    settings = _get_settings(db)

    try:
        pdf_bytes = generate_pdf_bytes(invoice, settings)
        send_proforma_email(invoice, settings, pdf_bytes)
        invoice.status = "sent"
        invoice.sent_at = datetime.utcnow()
        db.commit()
        return JSONResponse({"ok": True, "message": f"Proforma {invoice.buyer_email} adresine gönderildi."})
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ────────────────────────────────────────────────────────────────────
# PDF İNDİR
# ────────────────────────────────────────────────────────────────────

@router.get("/esk/proformalar/{invoice_id}/pdf")
def download_pdf(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result

    invoice = db.query(ProformaInvoice).filter(ProformaInvoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/esk/proformalar", status_code=302)

    settings = _get_settings(db)
    pdf_bytes = generate_pdf_bytes(invoice, settings)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice.pi_number}.pdf"'},
    )


# ────────────────────────────────────────────────────────────────────
# REVİZE — Mevcut proformadan yeni revizyon oluştur
# ────────────────────────────────────────────────────────────────────

@router.post("/esk/proformalar/{invoice_id}/revize")
def revise_proforma(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result
    current_user = result

    original = db.query(ProformaInvoice).filter(ProformaInvoice.id == invoice_id).first()
    if not original:
        return JSONResponse({"ok": False, "error": "Proforma bulunamadı."}, status_code=404)

    # Orijinal proformayı "revised" durumuna al
    original.status = "revised"

    # Yeni PI numarası — aynı yıl sıradaki numara
    new_pi = generate_next_pi_number(db)

    new_invoice = ProformaInvoice(
        pi_number        = new_pi,
        issue_date       = datetime.utcnow().strftime("%d.%m.%Y"),
        validity_days    = original.validity_days,
        incoterm         = original.incoterm,
        currency         = original.currency,
        buyer_company    = original.buyer_company,
        buyer_country    = original.buyer_country,
        buyer_address    = original.buyer_address,
        buyer_contact    = original.buyer_contact,
        buyer_phone      = original.buyer_phone,
        buyer_email      = original.buyer_email,
        loading_port     = original.loading_port,
        destination_port = original.destination_port,
        delivery_time    = original.delivery_time,
        payment_term     = original.payment_term,
        freight_cost     = original.freight_cost,
        bank_name        = original.bank_name,
        bank_iban        = original.bank_iban,
        bank_swift       = original.bank_swift,
        notes            = original.notes,
        revision_number  = original.revision_number + 1,
        parent_id        = original.id,
        status           = "draft",
        created_by       = current_user.id,
    )
    db.add(new_invoice)
    db.flush()

    # Kalemleri kopyala
    for item in original.items:
        db.add(ProformaItem(
            invoice_id          = new_invoice.id,
            line_number         = item.line_number,
            product_description = item.product_description,
            packaging           = item.packaging,
            quantity            = item.quantity,
            quantity_unit       = item.quantity_unit,
            unit_price          = item.unit_price,
            total               = item.total,
        ))

    db.commit()
    return JSONResponse({"ok": True, "new_id": new_invoice.id, "pi_number": new_pi})


# ────────────────────────────────────────────────────────────────────
# SİL
# ────────────────────────────────────────────────────────────────────

@router.post("/esk/proformalar/{invoice_id}/sil")
def delete_proforma(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    result = _require_permission(request, db, "proformalar")
    if isinstance(result, RedirectResponse):
        return result

    invoice = db.query(ProformaInvoice).filter(ProformaInvoice.id == invoice_id).first()
    if invoice:
        db.delete(invoice)
        db.commit()
    return RedirectResponse("/esk/proformalar", status_code=303)


# ────────────────────────────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ────────────────────────────────────────────────────────────────────

def _build_invoice_from_form(form, db) -> ProformaInvoice:
    """Form verilerinden yeni ProformaInvoice nesnesi oluşturur."""
    pi_number = form.get("pi_number") or generate_next_pi_number(db)
    invoice = ProformaInvoice(pi_number=pi_number)
    _update_invoice_from_form(invoice, form)
    return invoice


def _update_invoice_from_form(invoice: ProformaInvoice, form) -> None:
    """Form verilerini mevcut ProformaInvoice nesnesine uygular."""
    invoice.pi_number        = form.get("pi_number", invoice.pi_number)
    invoice.issue_date       = form.get("issue_date", "") or datetime.utcnow().strftime("%d.%m.%Y")
    invoice.validity_days    = _int(form.get("validity_days"), 15)
    invoice.incoterm         = form.get("incoterm", "")
    invoice.currency         = form.get("currency", "USD")
    invoice.buyer_company    = form.get("buyer_company", "")
    invoice.buyer_country    = form.get("buyer_country", "")
    invoice.buyer_address    = form.get("buyer_address", "")
    invoice.buyer_contact    = form.get("buyer_contact", "")
    invoice.buyer_phone      = form.get("buyer_phone", "")
    invoice.buyer_email      = form.get("buyer_email", "")
    invoice.loading_port     = form.get("loading_port", "")
    invoice.destination_port = form.get("destination_port", "")
    invoice.delivery_time    = form.get("delivery_time", "")
    invoice.payment_term     = form.get("payment_term", "")
    invoice.freight_cost     = _float(form.get("freight_cost"), 0.0)
    invoice.bank_name        = form.get("bank_name", "")
    invoice.bank_iban        = form.get("bank_iban", "")
    invoice.bank_swift       = form.get("bank_swift", "")
    invoice.notes            = form.get("notes", "")


def _save_items_from_form(form, invoice_id: int, db: Session) -> None:
    """
    Form'dan dinamik satır kalemlerini okur ve ProformaItem kayıtlarını oluşturur.
    Alan adları: desc_1, pkg_1, qty_1, unit_1, price_1 (1'den başlayarak)
    """
    line = 1
    while True:
        desc = form.get(f"desc_{line}")
        if desc is None:
            break
        if desc.strip():
            qty   = _float(form.get(f"qty_{line}"),   0.0)
            price = _float(form.get(f"price_{line}"), 0.0)
            db.add(ProformaItem(
                invoice_id          = invoice_id,
                line_number         = line,
                product_description = desc.strip(),
                packaging           = form.get(f"pkg_{line}", ""),
                quantity            = qty,
                quantity_unit       = form.get(f"unit_{line}", "PCS"),
                unit_price          = price,
                total               = round(qty * price, 2),
            ))
        line += 1


def _build_revision_chain(invoice: ProformaInvoice, db: Session) -> list:
    """
    Proformanın revizyon geçmişini döner (en eskiden en yeniye).
    """
    chain = [invoice]
    current = invoice
    # Üst revizyonları takip et
    while current.parent_id:
        parent = db.query(ProformaInvoice).filter(ProformaInvoice.id == current.parent_id).first()
        if not parent:
            break
        chain.insert(0, parent)
        current = parent
    return chain


def _int(val, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _float(val, default: float = 0.0) -> float:
    try:
        return float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        return default

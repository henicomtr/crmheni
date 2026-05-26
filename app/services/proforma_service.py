# -*- coding: utf-8 -*-
"""
Proforma servisi — PDF üretimi ve mail gönderimi.
PDF: xhtml2pdf (HTML → PDF, saf Python, harici bağımlılık gerektirmez)
Mail: smtplib standart kütüphanesi, PDF ek olarak gönderilir.
"""

import base64
import io
import os
import smtplib
import logging
import tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa
import xhtml2pdf.files as _xhtml2pdf_files

logger = logging.getLogger(__name__)

# Proje kök dizini — şablon klasörü için
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TEMPLATES_DIR = os.path.join(_PROJECT_ROOT, "templates")


# ── Windows NamedTemporaryFile yaması ────────────────────────────────────────
# xhtml2pdf, fontu NamedTemporaryFile'a yazıp dosyayı KAPAMADAN ReportLab'a
# geçiriyor. Windows'ta aynı dosya iki kez açılamaz → PermissionError.
# Çözüm: dosyayı yazıp kapatmak (delete=False), ReportLab adı üzerinden okur.
_original_get_named_tmp_file = _xhtml2pdf_files.BaseFile.get_named_tmp_file


def _windows_safe_get_named_tmp_file(self):
    data = self.get_data()
    suffix = getattr(self, "suffix", ".tmp")
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    if data:
        tmp.write(data)
        tmp.flush()
    tmp.close()
    if getattr(self, "path", None) is None:
        self.path = tmp.name
    return tmp


_xhtml2pdf_files.BaseFile.get_named_tmp_file = _windows_safe_get_named_tmp_file
# ─────────────────────────────────────────────────────────────────────────────


def _get_font_data_url() -> str:
    """
    Arial TTF'yi data URL'e çevirir.
    MIME tipi 'font/ttf' olmalı — xhtml2pdf bu değeri kontrol eder.
    """
    font_path = os.path.join(_PROJECT_ROOT, "static", "fonts", "arial.ttf")
    with open(font_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:font/ttf;base64,{encoded}"


def _render_pdf_html(invoice, settings) -> str:
    """Proforma HTML şablonunu Jinja2 ile render eder, PDF'e kaynak olur."""
    env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR))
    template = env.get_template("proforma_pdf.html")
    font_data_url = _get_font_data_url()
    return template.render(invoice=invoice, settings=settings, font_data_url=font_data_url)


def generate_pdf_bytes(invoice, settings) -> bytes:
    """
    ProformaInvoice nesnesini PDF'e dönüştürür.
    Dönen değer: PDF içeriği (bytes).
    """
    html_str = _render_pdf_html(invoice, settings)
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(
        src=html_str,
        dest=pdf_buffer,
        encoding="utf-8",
    )
    if pisa_status.err:
        raise RuntimeError(f"PDF oluşturma hatası: {pisa_status.err}")
    return pdf_buffer.getvalue()


def send_proforma_email(invoice, settings, pdf_bytes: bytes) -> None:
    """
    Proforma PDF'ini alıcıya mail olarak gönderir.
    SMTP ayarları SiteSettings tablosundan okunur.
    Ayarlar eksikse EnvironmentError fırlatır.
    """
    smtp_host = getattr(settings, "smtp_host", None) or os.getenv("SMTP_HOST")
    smtp_port = getattr(settings, "smtp_port", None) or int(os.getenv("SMTP_PORT", "587"))
    smtp_user = getattr(settings, "smtp_user", None) or os.getenv("SMTP_USER")
    smtp_pass = getattr(settings, "smtp_password", None) or os.getenv("SMTP_PASS")
    smtp_from = getattr(settings, "smtp_from_email", None) or os.getenv("SMTP_FROM") or smtp_user

    if not smtp_host or not smtp_user or not smtp_pass:
        raise EnvironmentError(
            f"SMTP ayarları eksik. "
            f"smtp_host={smtp_host!r}, smtp_user={smtp_user!r}, smtp_pass={'***' if smtp_pass else None!r}"
        )

    to_email = invoice.buyer_email
    if not to_email:
        raise ValueError("Alıcı e-posta adresi boş olamaz.")

    logger.info("[proforma] SMTP bağlantısı başlıyor: %s:%s", smtp_host, smtp_port)

    # ── Mail mesajını oluştur ──────────────────────────────────────────
    msg = MIMEMultipart()
    msg["From"]    = smtp_from
    msg["To"]      = to_email
    msg["Subject"] = f"Proforma Invoice – {invoice.pi_number}"

    # Mail gövdesi (sade metin)
    body_text = _build_email_body(invoice)
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    # PDF eki
    attachment = MIMEBase("application", "octet-stream")
    attachment.set_payload(pdf_bytes)
    encoders.encode_base64(attachment)
    filename = f"{invoice.pi_number}.pdf"
    attachment.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(attachment)

    # ── SMTP bağlantısı ve gönderim (10s timeout) ────────────────────
    # Port 465 → doğrudan SSL; diğerleri → STARTTLS (587, 25)
    port = int(smtp_port)
    if port == 465:
        with smtplib.SMTP_SSL(smtp_host, port, timeout=10) as server:
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [to_email], msg.as_bytes())
    else:
        with smtplib.SMTP(smtp_host, port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [to_email], msg.as_bytes())

    logger.info("[proforma] Mail gönderildi: %s → %s", invoice.pi_number, to_email)


def _build_email_body(invoice) -> str:
    """Mail gövdesi için sade metin oluşturur."""
    lines = [
        f"Dear {invoice.buyer_contact or invoice.buyer_company or 'Sir/Madam'},",
        "",
        "Please find attached our Proforma Invoice for your review.",
        "",
        f"  PI Number   : {invoice.pi_number}",
        f"  Date        : {invoice.issue_date}",
        f"  Validity    : {invoice.validity_days} days",
        f"  Incoterm    : {invoice.incoterm or '—'}",
        f"  Grand Total : {invoice.grand_total:,.2f} {invoice.currency}",
        "",
        "Should you have any questions or require any amendments, please do not hesitate to contact us.",
        "",
        "Best regards,",
        "Export Department",
        "Heni Kozmetik Kimya Sanayi Ticaret Ltd. Şti.",
        "export@heni.com.tr",
        "www.heni.com.tr",
    ]
    return "\n".join(lines)


def generate_next_pi_number(db) -> str:
    """
    Yıla özel sıralı PI numarası üretir.
    Örnek: PI-2026-001, PI-2026-002 ...
    """
    from app.models import ProformaInvoice
    year = datetime.utcnow().year
    prefix = f"PI-{year}-"
    last = (
        db.query(ProformaInvoice)
        .filter(ProformaInvoice.pi_number.like(f"{prefix}%"))
        .order_by(ProformaInvoice.id.desc())
        .first()
    )
    if last:
        try:
            seq = int(last.pi_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:03d}"

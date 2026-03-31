# -*- coding: utf-8 -*-
"""
Fiyatlandırma Motoru Route'ları — /esk/pricing/* altında çalışır.
JWT ile korumalıdır; 'pricing' iznini kontrol eder.
"""

from fastapi import APIRouter, Request, Form, Depends, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from typing import Optional

from .database import get_db
from .models import (
    User, StockItem,
    PricingProduct, FormulaItem,
    FinishedProduct, PackagingItem,
    PricingResult,
)
from .config import SECRET_KEY, ALGORITHM
from .services.pricing_service import (
    calculate_internal_cost,
    calculate_finished_cost,
    calculate_final_price,
    save_pricing_result,
    format_product_name,
)

router    = APIRouter()
templates = Jinja2Templates(directory="templates")


def _build_stock_groups(db: Session) -> list:
    """
    StockItem satırlarını isme göre gruplar ve ağırlıklı ortalama birim fiyatını hesaplar.
    Fiyatlandırma dropdown'larında her hammadde bir kez gösterilir.
    """
    items    = db.query(StockItem).order_by(StockItem.name).all()
    name_map: dict = {}

    for item in items:
        key = item.name
        if key not in name_map:
            name_map[key] = {
                "representative_id": item.id,
                "name":              item.name,
                "unit":              item.unit,
                "currency":          item.currency,
                "total_value":       0.0,
                "priced_qty":        0.0,
                "avg_price":         None,
            }
        g = name_map[key]
        if item.unit_price is not None:
            g["total_value"] += item.quantity * item.unit_price
            g["priced_qty"]  += item.quantity

    # Ağırlıklı ortalama fiyat hesapla
    for g in name_map.values():
        if g["priced_qty"] > 0:
            g["avg_price"] = g["total_value"] / g["priced_qty"]

    return list(name_map.values())


# ─────────────────────────────────────────────────────────────────────
# AUTH YARDIMCISI
# ─────────────────────────────────────────────────────────────────────

def _get_user(token: Optional[str], db: Session) -> Optional[User]:
    """JWT token'dan kullanıcı nesnesini döner; geçersizse None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email   = payload.get("sub")
        if not email:
            return None
        return db.query(User).filter(User.email == email).first()
    except JWTError:
        return None


def _auth_check(token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    """Token doğrular; geçersizse None döner."""
    return _get_user(token, db)


# ─────────────────────────────────────────────────────────────────────
# AŞAMA 1 — ÜRÜN & FORMÜL YÖNETİMİ
# ─────────────────────────────────────────────────────────────────────

@router.get("/esk/pricing", response_class=HTMLResponse)
def pricing_home(
    request: Request,
    db:      Session = Depends(get_db),
    token:   Optional[str] = Cookie(None),
):
    """Fiyatlandırma ana sayfası — 3 aşama sekmeli."""
    user = _get_user(token, db)
    if not user:
        return RedirectResponse("/esk/login", status_code=302)
    if not user.has_permission("pricing"):
        return RedirectResponse("/esk/dashboard", status_code=302)

    # Stok kalemleri — dropdown'lar için isme göre grupla, ort. fiyatla göster
    stock_items = _build_stock_groups(db)

    # Formül tablosu için isim → ort. fiyat sözlüğü (template'de batch fiyatı yerine kullanılır)
    stock_avg_map = {g["name"]: g for g in stock_items}

    # Fiyatlandırma ürünleri
    pricing_products = db.query(PricingProduct).order_by(PricingProduct.name).all()

    # Son ürünler + ilgili fiyat sonuçları
    finished_products = (
        db.query(FinishedProduct)
        .order_by(FinishedProduct.id.desc())
        .all()
    )

    # Son PricingResult snapshot'ları (finished_product_id → result)
    latest_results: dict = {}
    for fp in finished_products:
        if fp.pricing_results:
            latest_results[fp.id] = sorted(
                fp.pricing_results, key=lambda r: r.calculated_at, reverse=True
            )[0]

    return templates.TemplateResponse("admin_pricing.html", {
        "request":          request,
        "current_user":     user,
        "stock_items":      stock_items,
        "stock_avg_map":    stock_avg_map,
        "pricing_products": pricing_products,
        "finished_products": finished_products,
        "latest_results":   latest_results,
    })


@router.post("/esk/pricing/products")
def create_pricing_product(
    request:     Request,
    name:        str     = Form(...),
    notes:       str     = Form(""),
    db:          Session = Depends(get_db),
    token:       Optional[str] = Cookie(None),
):
    """Yeni fiyatlandırma ürünü oluşturur."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    # Ürün adını title case'e formatla
    formatted_name = format_product_name(name)

    product = PricingProduct(
        name  = formatted_name,
        notes = notes.strip() or None,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return RedirectResponse(f"/esk/pricing?tab=1&product_id={product.id}", status_code=302)


@router.post("/esk/pricing/products/{product_id}/formula")
def add_formula_item(
    request:           Request,
    product_id:        int,
    stock_item_id:     int   = Form(...),
    kg_per_ton:        float = Form(...),
    db:                Session = Depends(get_db),
    token:             Optional[str] = Cookie(None),
):
    """Bir fiyatlandırma ürününe formül satırı ekler."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    # Aynı stok kalemi zaten ekliyse üzerine yaz
    existing = db.query(FormulaItem).filter(
        FormulaItem.pricing_product_id == product_id,
        FormulaItem.stock_item_id      == stock_item_id,
    ).first()

    if existing:
        existing.kg_per_ton = kg_per_ton
    else:
        db.add(FormulaItem(
            pricing_product_id = product_id,
            stock_item_id      = stock_item_id,
            kg_per_ton         = kg_per_ton,
        ))

    db.commit()
    return RedirectResponse(f"/esk/pricing?tab=1&product_id={product_id}", status_code=302)


@router.post("/esk/pricing/formula-items/{item_id}/delete")
def delete_formula_item(
    request: Request,
    item_id: int,
    db:      Session = Depends(get_db),
    token:   Optional[str] = Cookie(None),
):
    """Formül satırını siler."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    item = db.query(FormulaItem).filter(FormulaItem.id == item_id).first()
    if item:
        product_id = item.pricing_product_id
        db.delete(item)
        db.commit()
        return RedirectResponse(f"/esk/pricing?tab=1&product_id={product_id}", status_code=302)

    return RedirectResponse("/esk/pricing?tab=1", status_code=302)


@router.get("/esk/pricing/products/{product_id}/calculate")
def api_calculate_internal(
    product_id: int,
    db:         Session = Depends(get_db),
    token:      Optional[str] = Cookie(None),
):
    """AJAX: Aşama 1 — Dinamik iç maliyet hesapla (JSON döner)."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return JSONResponse({"error": "Yetkisiz erişim"}, status_code=403)

    result = calculate_internal_cost(db, product_id)
    return JSONResponse(result)


@router.post("/esk/pricing/products/{product_id}/delete")
def delete_pricing_product(
    request:    Request,
    product_id: int,
    db:         Session = Depends(get_db),
    token:      Optional[str] = Cookie(None),
):
    """Fiyatlandırma ürününü ve ilgili tüm verileri siler."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    product = db.query(PricingProduct).filter(PricingProduct.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()

    return RedirectResponse("/esk/pricing?tab=1", status_code=302)


# ─────────────────────────────────────────────────────────────────────
# AŞAMA 2 — SON ÜRÜN & AMBALAJ YÖNETİMİ
# ─────────────────────────────────────────────────────────────────────

@router.post("/esk/pricing/finished")
def create_finished_product(
    request:           Request,
    pricing_product_id: int   = Form(...),
    volume_liters:      float = Form(...),
    label:              str   = Form(""),
    db:                Session = Depends(get_db),
    token:             Optional[str] = Cookie(None),
):
    """Yeni son ürün (ambalajlı) oluşturur."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    # Etiket boşsa otomatik üret
    auto_label = label.strip() or f"{volume_liters:g}L"

    finished = FinishedProduct(
        pricing_product_id = pricing_product_id,
        volume_liters      = volume_liters,
        label              = auto_label,
    )
    db.add(finished)
    db.commit()
    db.refresh(finished)
    return RedirectResponse(f"/esk/pricing?tab=2&finished_id={finished.id}", status_code=302)


@router.post("/esk/pricing/finished/{finished_id}/packaging")
def add_packaging_item(
    request:            Request,
    finished_id:        int,
    stock_item_id:      int   = Form(...),
    component_type:     str   = Form(...),
    quantity_per_unit:  float = Form(1.0),
    units_per_box:      Optional[int] = Form(None),
    db:                Session = Depends(get_db),
    token:             Optional[str] = Cookie(None),
):
    """Son ürüne ambalaj bileşeni ekler."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    # Aynı bileşen tipi zaten ekliyse üzerine yaz
    existing = db.query(PackagingItem).filter(
        PackagingItem.finished_product_id == finished_id,
        PackagingItem.component_type      == component_type,
    ).first()

    if existing:
        existing.stock_item_id     = stock_item_id
        existing.quantity_per_unit = quantity_per_unit
        existing.units_per_box     = units_per_box
    else:
        db.add(PackagingItem(
            finished_product_id = finished_id,
            stock_item_id       = stock_item_id,
            component_type      = component_type,
            quantity_per_unit   = quantity_per_unit,
            units_per_box       = units_per_box,
        ))

    db.commit()
    return RedirectResponse(f"/esk/pricing?tab=2&finished_id={finished_id}", status_code=302)


@router.post("/esk/pricing/packaging-items/{item_id}/delete")
def delete_packaging_item(
    request: Request,
    item_id: int,
    db:      Session = Depends(get_db),
    token:   Optional[str] = Cookie(None),
):
    """Ambalaj bileşenini siler."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    item = db.query(PackagingItem).filter(PackagingItem.id == item_id).first()
    if item:
        finished_id = item.finished_product_id
        db.delete(item)
        db.commit()
        return RedirectResponse(f"/esk/pricing?tab=2&finished_id={finished_id}", status_code=302)

    return RedirectResponse("/esk/pricing?tab=2", status_code=302)


@router.get("/esk/pricing/finished/{finished_id}/calculate")
def api_calculate_finished(
    finished_id: int,
    db:          Session = Depends(get_db),
    token:       Optional[str] = Cookie(None),
):
    """AJAX: Aşama 2 — Dinamik son ürün maliyeti hesapla (JSON döner)."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return JSONResponse({"error": "Yetkisiz erişim"}, status_code=403)

    result = calculate_finished_cost(db, finished_id)
    return JSONResponse(result)


@router.post("/esk/pricing/finished/{finished_id}/delete")
def delete_finished_product(
    request:     Request,
    finished_id: int,
    db:          Session = Depends(get_db),
    token:       Optional[str] = Cookie(None),
):
    """Son ürünü ve ilgili tüm verileri siler."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    finished = db.query(FinishedProduct).filter(FinishedProduct.id == finished_id).first()
    if finished:
        db.delete(finished)
        db.commit()

    return RedirectResponse("/esk/pricing?tab=2", status_code=302)


# ─────────────────────────────────────────────────────────────────────
# AŞAMA 3 — NİHAİ SATIŞ FİYATI
# ─────────────────────────────────────────────────────────────────────

@router.get("/esk/pricing/finished/{finished_id}/final-calculate")
def api_calculate_final(
    finished_id:   int,
    overhead_rate: float = 0.20,
    profit_rate:   float = 0.25,
    db:            Session = Depends(get_db),
    token:         Optional[str] = Cookie(None),
):
    """AJAX: Aşama 3 — Nihai satış fiyatını hesapla (JSON döner, kaydetmez)."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return JSONResponse({"error": "Yetkisiz erişim"}, status_code=403)

    stage2 = calculate_finished_cost(db, finished_id)
    if "error" in stage2:
        return JSONResponse(stage2, status_code=404)

    stage3 = calculate_final_price(
        finished_cost = stage2["total_unit_cost"],
        overhead_rate = overhead_rate,
        profit_rate   = profit_rate,
    )

    # Ürün etiketini de döndür
    finished = db.query(FinishedProduct).filter(FinishedProduct.id == finished_id).first()
    product_name = ""
    if finished and finished.pricing_product:
        product_name = finished.pricing_product.name

    return JSONResponse({
        "product_name": product_name,
        "label":        stage2["label"],
        "stage2":       stage2,
        "stage3":       stage3,
    })


@router.post("/esk/pricing/results")
def save_result(
    request:        Request,
    finished_id:    int   = Form(...),
    overhead_rate:  float = Form(0.20),
    profit_rate:    float = Form(0.25),
    db:             Session = Depends(get_db),
    token:          Optional[str] = Cookie(None),
):
    """Nihai fiyatı PricingResult olarak kaydeder (snapshot)."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    save_pricing_result(
        db                  = db,
        finished_product_id = finished_id,
        overhead_rate       = overhead_rate,
        profit_rate         = profit_rate,
    )
    return RedirectResponse(f"/esk/pricing?tab=3&finished_id={finished_id}", status_code=302)


@router.post("/esk/pricing/results/{result_id}/delete")
def delete_pricing_result(
    request:   Request,
    result_id: int,
    db:        Session = Depends(get_db),
    token:     Optional[str] = Cookie(None),
):
    """Kaydedilmiş fiyat sonucunu siler."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    result = db.query(PricingResult).filter(PricingResult.id == result_id).first()
    if result:
        db.delete(result)
        db.commit()

    return RedirectResponse("/esk/pricing/export", status_code=302)


@router.get("/esk/pricing/export", response_class=HTMLResponse)
def pricing_export(
    request: Request,
    db:      Session = Depends(get_db),
    token:   Optional[str] = Cookie(None),
):
    """Tüm kaydedilmiş fiyatları liste olarak gösterir (export sayfası)."""
    user = _get_user(token, db)
    if not user or not user.has_permission("pricing"):
        return RedirectResponse("/esk/login", status_code=302)

    from sqlalchemy.orm import joinedload

    results = (
        db.query(PricingResult)
        .options(
            joinedload(PricingResult.finished_product)
            .joinedload(FinishedProduct.pricing_product)
        )
        .order_by(PricingResult.calculated_at.desc())
        .all()
    )

    return templates.TemplateResponse("admin_pricing.html", {
        "request":           request,
        "current_user":      user,
        "export_mode":       True,
        "results":           results,
        "stock_items":       [],
        "pricing_products":  [],
        "finished_products": [],
        "latest_results":    {},
    })
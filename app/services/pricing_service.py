"""
Fiyatlandırma Servisi — 3 aşamalı maliyet hesaplama iş mantığı.
Tüm maliyetler USD cinsinden hesaplanır; döviz dönüşümü currency_service üzerinden yapılır.
"""

from __future__ import annotations

import json
from typing import Optional
from sqlalchemy.orm import Session

from ..models import (
    PricingProduct,
    FormulaItem,
    FinishedProduct,
    PackagingItem,
    PricingResult,
    StockItem,
)
from .currency_service import get_rates


def _get_avg_unit_price(db: Session, stock: StockItem) -> float:
    """
    Aynı isimli tüm StockItem partilerinin ağırlıklı ortalama birim fiyatını döner.
    Yalnızca fiyatı girilmiş partiler hesaba katılır.
    Eşleşen parti yoksa veya hiçbir fiyat girilmemişse 0.0 döner.
    """
    batches = db.query(StockItem).filter(StockItem.name == stock.name).all()
    total_value  = sum(b.quantity * b.unit_price for b in batches if b.unit_price is not None)
    priced_qty   = sum(b.quantity for b in batches if b.unit_price is not None)
    if priced_qty > 0:
        return total_value / priced_qty
    return 0.0


# ─────────────────────────────────────────────────────────────────────
# YARDIMCI: Döviz Dönüşümü
# ─────────────────────────────────────────────────────────────────────

def _to_usd(amount: float, currency: str, rates: dict) -> float:
    """
    Herhangi bir para birimindeki tutarı USD'ye çevirir.
    Desteklenen: USD, TRY, EUR
    """
    if not amount:
        return 0.0
    currency = (currency or "USD").upper()
    if currency == "USD":
        return amount
    elif currency == "TRY":
        usd_try = rates.get("USD_TRY", 43.50)
        return amount / usd_try if usd_try else 0.0
    elif currency == "EUR":
        eur_usd = rates.get("EUR_USD", 1.08)
        return amount * eur_usd
    # Bilinmeyen para birimi — olduğu gibi döndür
    return amount


def _fmt(value: float, decimals: int = 2) -> float:
    """Sayıyı belirtilen ondalık basamağa yuvarlar."""
    return round(value, decimals)


# ─────────────────────────────────────────────────────────────────────
# AŞAMA 1 — İç Maliyet (Formülasyon)
# ─────────────────────────────────────────────────────────────────────

def calculate_internal_cost(db: Session, pricing_product_id: int) -> dict:
    """
    Bir PricingProduct'ın ton başına iç maliyetini dinamik olarak hesaplar.
    Her stok kaleminin kendi para birimi USD'ye çevrilir (TCMB günlük kur).

    Dönüş:
        {
            "product_id": int,
            "product_name": str,
            "formula_items": [...],
            "total_cost_per_ton": float,   # USD/ton
            "total_kg": float,
            "rates": dict,                 # kullanılan kurlar
            "warning": str | None
        }
    """
    pricing_product = db.query(PricingProduct).filter(
        PricingProduct.id == pricing_product_id
    ).first()

    if not pricing_product:
        return {"error": "Ürün bulunamadı"}

    # Kurları bir kez çek — tüm kalemler aynı anlık kurla hesaplanır
    rates = get_rates()

    items_detail = []
    total_cost   = 0.0
    total_kg     = 0.0

    for fi in pricing_product.formula_items:
        stock    = fi.stock_item
        currency = (stock.currency if stock else "USD") or "USD"

        # Aynı isimli tüm partilerin ağırlıklı ortalama birim fiyatı
        unit_price_orig = _get_avg_unit_price(db, stock) if stock else 0.0

        # USD'ye çevrilmiş birim fiyat
        unit_price_usd = _to_usd(unit_price_orig, currency, rates)

        kg            = fi.kg_per_ton or 0.0
        line_cost_usd = unit_price_usd * kg   # USD cinsinden hat maliyeti

        total_cost += line_cost_usd
        total_kg   += kg

        items_detail.append({
            "formula_item_id":  fi.id,
            "stock_item_id":    fi.stock_item_id,
            "stock_item_name":  stock.name if stock else "— Silinmiş —",
            "unit":             stock.unit if stock else "",
            # Orijinal fiyat (gösterim için — kafa karışıklığını önlemek için 2 ondalık)
            "unit_price_orig":  _fmt(unit_price_orig, 2),
            "currency":         currency,
            # USD karşılığı (hesaplama için)
            "unit_price_usd":   _fmt(unit_price_usd, 4),
            "kg_per_ton":       kg,
            # Hat maliyeti: USD, 2 ondalık basamak
            "line_cost_usd":    _fmt(line_cost_usd, 2),
        })

    # Formül ağırlığı uyarısı
    warning = None
    if abs(total_kg - 1000.0) > 5.0:
        warning = f"Toplam formül ağırlığı {total_kg:.1f} kg — 1000 kg olması beklenir."

    return {
        "product_id":         pricing_product.id,
        "product_name":       pricing_product.name,
        "formula_items":      items_detail,
        "total_cost_per_ton": _fmt(total_cost, 2),
        "total_kg":           round(total_kg, 2),
        "rates": {
            "USD_TRY": _fmt(rates.get("USD_TRY", 0), 2),
            "EUR_TRY": _fmt(rates.get("EUR_TRY", 0), 2),
            "EUR_USD": _fmt(rates.get("EUR_USD", 0), 4),
            "source":  rates.get("source", "?"),
            "updated": rates.get("updated", "—"),
        },
        "warning": warning,
    }


# ─────────────────────────────────────────────────────────────────────
# AŞAMA 2 — Son Ürün Maliyeti (Ambalajlı)
# ─────────────────────────────────────────────────────────────────────

def calculate_finished_cost(db: Session, finished_product_id: int) -> dict:
    """
    Ambalajlı son ürünün birim maliyetini hesaplar. Tüm değerler USD.

    Formül:
        ham_madde_maliyeti = (ton_başına_maliyet / 1000) * hacim_litre
        ambalaj_maliyeti   = Σ bileşen maliyetleri (USD'ye çevrilmiş)
        toplam             = ham_madde_maliyeti + ambalaj_maliyeti
    """
    finished = db.query(FinishedProduct).filter(
        FinishedProduct.id == finished_product_id
    ).first()

    if not finished:
        return {"error": "Son ürün bulunamadı"}

    # Kurları bir kez çek
    rates = get_rates()

    # Aşama 1 — dinamik iç maliyet
    stage1 = calculate_internal_cost(db, finished.pricing_product_id)
    if "error" in stage1:
        return stage1

    cost_per_ton = stage1["total_cost_per_ton"]
    volume       = finished.volume_liters or 0.0
    raw_mat_cost = _fmt((cost_per_ton / 1000.0) * volume, 4)

    packaging_breakdown = []
    packaging_cost      = 0.0

    for pi in finished.packaging_items:
        stock    = pi.stock_item
        currency = (stock.currency if stock else "USD") or "USD"

        # Aynı isimli tüm partilerin ağırlıklı ortalama birim fiyatı
        unit_price_orig = _get_avg_unit_price(db, stock) if stock else 0.0
        unit_price_usd  = _to_usd(unit_price_orig, currency, rates)

        qty = pi.quantity_per_unit or 1.0

        # Koli: maliyet = (koli_fiyatı / kolide_adet) * adet
        if pi.component_type == "koli" and pi.units_per_box and pi.units_per_box > 0:
            component_cost_usd = (unit_price_usd / pi.units_per_box) * qty
        else:
            component_cost_usd = unit_price_usd * qty

        packaging_cost += component_cost_usd

        packaging_breakdown.append({
            "packaging_item_id":  pi.id,
            "stock_item_id":      pi.stock_item_id,
            "stock_item_name":    stock.name if stock else "— Silinmiş —",
            "component_type":     pi.component_type,
            "unit_price_orig":    _fmt(unit_price_orig, 2),
            "currency":           currency,
            "unit_price_usd":     _fmt(unit_price_usd, 4),
            "quantity_per_unit":  qty,
            "units_per_box":      pi.units_per_box,
            "line_cost_usd":      _fmt(component_cost_usd, 4),
        })

    packaging_cost  = _fmt(packaging_cost, 4)
    total_unit_cost = _fmt(raw_mat_cost + packaging_cost, 4)

    warning = stage1.get("warning")
    missing = [p["stock_item_name"] for p in packaging_breakdown if p["unit_price_orig"] == 0.0]
    if missing:
        msg     = f"Fiyatı girilmemiş bileşenler: {', '.join(missing)}"
        warning = f"{warning} | {msg}" if warning else msg

    return {
        "finished_product_id":   finished.id,
        "label":                 finished.label or f"{volume}L",
        "volume_liters":         volume,
        "internal_cost_per_ton": cost_per_ton,
        "raw_material_cost":     raw_mat_cost,
        "packaging_breakdown":   packaging_breakdown,
        "packaging_cost":        packaging_cost,
        "total_unit_cost":       total_unit_cost,
        "rates":                 stage1["rates"],
        "warning":               warning,
    }


# ─────────────────────────────────────────────────────────────────────
# AŞAMA 3 — Nihai Satış Fiyatı
# ─────────────────────────────────────────────────────────────────────

def calculate_final_price(
    finished_cost: float,
    overhead_rate: float = 0.20,
    profit_rate:   float = 0.25,
) -> dict:
    """
    Nihai satış fiyatını hesaplar.
    final_price = finished_cost × (1 + overhead_rate) × (1 + profit_rate)
    """
    after_overhead = finished_cost * (1 + overhead_rate)
    final_price    = after_overhead * (1 + profit_rate)

    return {
        "finished_cost":   _fmt(finished_cost, 4),
        "overhead_rate":   overhead_rate,
        "profit_rate":     profit_rate,
        "overhead_amount": _fmt(after_overhead - finished_cost, 4),
        "profit_amount":   _fmt(final_price - after_overhead, 4),
        "final_price":     _fmt(final_price, 4),
    }


def save_pricing_result(
    db:                  Session,
    finished_product_id: int,
    overhead_rate:       float = 0.20,
    profit_rate:         float = 0.25,
) -> Optional[PricingResult]:
    """
    Aşama 2 + 3'ü hesaplayıp PricingResult olarak veritabanına kaydeder.
    """
    stage2 = calculate_finished_cost(db, finished_product_id)
    if "error" in stage2:
        return None

    stage3 = calculate_final_price(
        finished_cost=stage2["total_unit_cost"],
        overhead_rate=overhead_rate,
        profit_rate=profit_rate,
    )

    breakdown = {
        "rates":  stage2.get("rates"),
        "stage2": stage2,
        "stage3": stage3,
    }

    result = PricingResult(
        finished_product_id   = finished_product_id,
        internal_cost_per_ton = stage2["internal_cost_per_ton"],
        raw_material_cost     = stage2["raw_material_cost"],
        packaging_cost        = stage2["packaging_cost"],
        total_unit_cost       = stage2["total_unit_cost"],
        overhead_rate         = overhead_rate,
        profit_rate           = profit_rate,
        final_price           = stage3["final_price"],
    )
    result.set_breakdown(breakdown)

    db.add(result)
    db.commit()
    db.refresh(result)
    return result


# ─────────────────────────────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────────────────────────────

def format_product_name(raw_name: str) -> str:
    """Ürün adını Türkçe title case'e dönüştürür."""
    tr_map = {"i": "İ", "ı": "I", "ğ": "Ğ", "ü": "Ü", "ş": "Ş", "ö": "Ö", "ç": "Ç"}
    words  = raw_name.strip().split()
    result = []
    for word in words:
        if not word:
            continue
        first       = word[0]
        upper_first = tr_map.get(first, first.upper())
        result.append(upper_first + word[1:])
    return " ".join(result)
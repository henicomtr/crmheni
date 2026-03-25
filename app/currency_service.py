"""
currency_service.py
TCMB today.xml'den USD/TRY ve EUR/TRY kurlarını çeker.
Sonuçları 1 saat bellekte cache'ler — her istek XML çekmez.
"""
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

try:
    import requests
    _has_requests = True
except ImportError:
    import urllib.request
    _has_requests = False

TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"

# Fallback: TCMB'ye ulaşılamazsa kullanılacak sabit kurlar
FALLBACK_RATES = {
    "USD_TRY": 43.50,
    "EUR_TRY": 47.00,
    "EUR_USD": 1.08,
}

_cache: dict = {}
_cache_lock  = threading.Lock()
CACHE_TTL    = 3600  # 1 saat (saniye)


def _fetch_xml() -> Optional[str]:
    """TCMB XML'ini string olarak döner, hata varsa None."""
    try:
        if _has_requests:
            r = requests.get(TCMB_URL, timeout=8)
            r.raise_for_status()
            return r.content
        else:
            with urllib.request.urlopen(TCMB_URL, timeout=8) as resp:
                return resp.read()
    except Exception as e:
        print(f"[currency_service] TCMB XML fetch hatası: {e}")
        return None


def _parse_rates(xml_bytes: bytes) -> dict:
    """XML'den USD/TRY ve EUR/TRY ForexSelling kurlarını çıkarır."""
    rates = {}
    try:
        root = ET.fromstring(xml_bytes)
        for currency in root.findall("Currency"):
            code = currency.get("CurrencyCode", "")
            selling = currency.findtext("ForexSelling")
            if selling and code in ("USD", "EUR"):
                try:
                    rates[code] = float(selling.replace(",", "."))
                except ValueError:
                    pass
    except Exception as e:
        print(f"[currency_service] XML parse hatası: {e}")
    return rates


def get_rates() -> dict:
    """
    Güncel kurları döner:
    {
        "USD_TRY": float,
        "EUR_TRY": float,
        "EUR_USD": float,   # çapraz kur
        "source":  "tcmb" | "fallback",
        "updated": "HH:MM" | "—",
    }
    """
    with _cache_lock:
        now = time.time()
        if _cache.get("expires", 0) > now:
            return _cache["rates"]

    # Cache dolmamış veya boş — TCMB'yi çek
    xml_bytes = _fetch_xml()
    rates     = {}

    if xml_bytes:
        rates = _parse_rates(xml_bytes)

    if "USD" in rates and "EUR" in rates:
        result = {
            "USD_TRY": rates["USD"],
            "EUR_TRY": rates["EUR"],
            "EUR_USD": rates["EUR"] / rates["USD"],   # çapraz
            "source":  "tcmb",
            "updated": datetime.now().strftime("%H:%M"),
        }
    else:
        # TCMB'ye ulaşılamadı — önceki cache'i koru, yoksa fallback
        with _cache_lock:
            if _cache.get("rates"):
                return _cache["rates"]
        result = {**FALLBACK_RATES, "source": "fallback", "updated": "—"}

    with _cache_lock:
        _cache["rates"]   = result
        _cache["expires"] = time.time() + CACHE_TTL

    return result


def convert(amount_usd: float, target_currency: str, rates: dict) -> tuple[float, str]:
    """
    USD cinsinden tutarı hedef para birimine çevirir.
    Returns (converted_amount, symbol)
    """
    if target_currency == "USD":
        return amount_usd, "$"
    elif target_currency == "TRY":
        return amount_usd * rates.get("USD_TRY", FALLBACK_RATES["USD_TRY"]), "₺"
    elif target_currency == "EUR":
        return amount_usd / rates.get("EUR_USD", FALLBACK_RATES["EUR_USD"]), "€"
    return amount_usd, "$"


LANG_CURRENCY = {
    "en": "USD",
    "tr": "TRY",
    "de": "EUR",
    "fr": "EUR",
    "ar": "USD",
    "ru": "EUR",
    "es": "EUR",
}


def format_price(amount_usd: float, lang: str, rates: dict) -> str:
    """
    Dile göre fiyatı formatlanmış string olarak döner.
    EN → $1,234.50
    TR → 53.750,00 ₺
    DE → 1.150,25 €
    FR → 1 150,25 €
    """
    currency = LANG_CURRENCY.get(lang, "USD")
    value, symbol = convert(amount_usd, currency, rates)

    if lang in ("en", "ar"):
        return f"{symbol}{value:,.2f}"
    elif lang == "tr":
        # Türk formatı: nokta binlik ayırıcı, virgül ondalık
        formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{formatted} {symbol}"
    else:  # de, fr, ru, es
        formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{formatted} {symbol}"
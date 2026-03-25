# app/lang.py
# =========================================================
# Dil tespiti ve yardımcı fonksiyonlar
# =========================================================

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
import re

SUPPORTED_LANGS = ["en", "tr", "de", "fr", "ar", "ru", "es"]
DEFAULT_LANG    = "en"
LANG_COOKIE     = "heni_lang"

# Showroom URL'leri — bunlar dil prefix'i gerektirir
LANG_PREFIXED_PATHS = ["/showroom", "/product/", "/basket", "/add-to-cart",
                        "/update-cart", "/remove-from-cart", "/quote-request"]

# Admin ve statik URL'ler — prefix gerekmez
SKIP_PREFIXES = ["/admin", "/static", "/favicon"]


def detect_lang(request: Request) -> str:
    """Dili şu sırayla tespit eder: URL prefix → cookie → Accept-Language → default."""

    # 1. URL prefix
    path = request.url.path
    parts = path.strip("/").split("/")
    if parts and parts[0] in SUPPORTED_LANGS:
        return parts[0]

    # 2. Cookie
    cookie_lang = request.cookies.get(LANG_COOKIE)
    if cookie_lang in SUPPORTED_LANGS:
        return cookie_lang

    # 3. Accept-Language header
    accept = request.headers.get("accept-language", "")
    for segment in re.split(r"[,;]", accept):
        code = segment.strip()[:2].lower()
        if code in SUPPORTED_LANGS:
            return code

    return DEFAULT_LANG


def strip_lang_prefix(path: str) -> str:
    """URL'den dil prefix'ini temizler: /tr/showroom → /showroom"""
    parts = path.strip("/").split("/")
    if parts and parts[0] in SUPPORTED_LANGS:
        return "/" + "/".join(parts[1:])
    return path


def add_lang_prefix(lang: str, path: str) -> str:
    """Path'e dil prefix ekler: /showroom → /tr/showroom"""
    clean = strip_lang_prefix(path)
    if lang == DEFAULT_LANG:
        return clean  # EN prefix'siz: /showroom
    return f"/{lang}{clean}"


class LangMiddleware(BaseHTTPMiddleware):
    """
    Showroom sayfalarına dil prefix'i olmadan gelinirse,
    doğru dile yönlendirir ve cookie set eder.

    Örnek:
      GET /showroom           → 302 /showroom       (EN, prefix'siz)
      GET /showroom           → 302 /tr/showroom    (TR cookie varsa)
      GET /tr/showroom        → pass through (cookie günceller)
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Admin, static vb. — dokunma
        for skip in SKIP_PREFIXES:
            if path.startswith(skip):
                return await call_next(request)

        # Showroom scope mu?
        clean_path = strip_lang_prefix(path)
        is_showroom = any(
            clean_path == p or clean_path.startswith(p)
            for p in LANG_PREFIXED_PATHS
        )

        if not is_showroom:
            return await call_next(request)

        # URL'de prefix var mı?
        parts = path.strip("/").split("/")
        url_lang = parts[0] if parts and parts[0] in SUPPORTED_LANGS else None

        if url_lang:
            # Prefix var → cookie güncelle, devam et
            response = await call_next(request)
            response.set_cookie(LANG_COOKIE, url_lang, max_age=60*60*24*365, samesite="lax")
            return response
        else:
            # Prefix yok → dil tespit et, yönlendir
            lang = detect_lang(request)
            target = add_lang_prefix(lang, path)
            query = str(request.url.query)
            if query:
                target = f"{target}?{query}"
            response = RedirectResponse(url=target, status_code=302)
            response.set_cookie(LANG_COOKIE, lang, max_age=60*60*24*365, samesite="lax")
            return response
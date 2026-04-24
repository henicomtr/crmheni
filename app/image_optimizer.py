# -*- coding: utf-8 -*-
"""
Görsel optimizasyon modülü.

Hem upload anında (route'lardan çağrılır) hem de toplu işleme (CLI) için kullanılır.
"""

import os
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional

from PIL import Image, ImageOps

# Srcset boyutları: anahtar → (max_genişlik, webp_kalite)
SRCSET_BOYUTLARI = {
    "sm": (480, 80),
    "md": (800, 82),
    "lg": (1200, 85),
}

# Ana WebP kalitesi
VARSAYILAN_KALITE = 82

# Maksimum genişlik (daha geniş görseller yeniden boyutlandırılır)
MAKS_GENISLIK = 1200

# Bu değerden geniş görsellerde srcset versiyonları üretilir
SRCSET_MIN_GENISLIK = 600


@dataclass
class OptimizasyonSonucu:
    webp: str                          # Ana WebP dosya adı
    original: Optional[str]            # _original yedek dosya adı
    srcset: Optional[dict]             # {'sm': ..., 'md': ..., 'lg': ...} veya None
    kazanilan_kb: float                # Kazanılan boyut (KB)
    genislik: int
    yukseklik: int


def optimize_gorsel(
    icerik: bytes,
    orijinal_dosya_adi: str,
    cikti_klasoru: str,
    logo_mu: bool = False,
    uid: Optional[str] = None,
) -> OptimizasyonSonucu:
    """
    Upload edilen görseli optimize eder.

    - logo_mu=False: WebP'e dönüştür, srcset üret (>600px görsellerde)
    - logo_mu=True:  WebP'e dönüştür, RGBA şeffaflığını koru, srcset üretme
    - Orijinal dosyayı _original suffix ile yedekle
    - EXIF verisi WebP kaydetme sırasında otomatik temizlenir
    - Hata durumunda ValueError fırlatır (çağıran ham veriyi kaydedebilir)
    """
    if uid is None:
        uid = uuid.uuid4().hex[:12]

    os.makedirs(cikti_klasoru, exist_ok=True)

    orijinal_uzanti = os.path.splitext(orijinal_dosya_adi)[1].lower()
    orijinal_boyut_kb = len(icerik) / 1024

    # Orijinal yedeği kaydet
    orijinal_dosya = f"img_{uid}_original{orijinal_uzanti}"
    orijinal_yol = os.path.join(cikti_klasoru, orijinal_dosya)
    with open(orijinal_yol, "wb") as f:
        f.write(icerik)

    img = Image.open(BytesIO(icerik))
    img.load()

    # EXIF rotasyonunu uygula (telefon fotoğrafları için)
    img = ImageOps.exif_transpose(img)

    gercek_genislik, gercek_yukseklik = img.width, img.height
    resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS

    if logo_mu:
        # Logo: şeffaflığı koru, srcset üretme
        if img.mode == "P":
            img = img.convert("RGBA")
        elif img.mode not in ("RGBA", "RGB", "LA", "L"):
            img = img.convert("RGBA")

        # Logo max 600px geniş
        logo_maks = 600
        if img.width > logo_maks:
            oran = logo_maks / img.width
            yeni_y = int(img.height * oran)
            img = img.resize((logo_maks, yeni_y), resample)

        webp_dosya = f"img_{uid}.webp"
        webp_yol = os.path.join(cikti_klasoru, webp_dosya)
        # lossless=True logolar için daha keskin kenarlar sağlar
        img.save(webp_yol, "WEBP", lossless=True, method=6)

        kazanilan = orijinal_boyut_kb - os.path.getsize(webp_yol) / 1024
        return OptimizasyonSonucu(
            webp=webp_dosya,
            original=orijinal_dosya,
            srcset=None,
            kazanilan_kb=round(kazanilan, 1),
            genislik=img.width,
            yukseklik=img.height,
        )

    # Normal görsel: max 1200px sınırla
    if img.width > MAKS_GENISLIK:
        oran = MAKS_GENISLIK / img.width
        yeni_y = int(img.height * oran)
        img = img.resize((MAKS_GENISLIK, yeni_y), resample)

    # RGB'ye çevir (WebP lossy için alfa flatten)
    if img.mode in ("RGBA", "LA"):
        alfa = img.split()[-1]
        zemin = Image.new("RGB", img.size, (255, 255, 255))
        zemin.paste(img.convert("RGB"), mask=alfa)
        img = zemin
    elif img.mode == "P":
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Ana WebP kaydet (EXIF Pillow tarafından otomatik temizlenir)
    webp_dosya = f"img_{uid}.webp"
    webp_yol = os.path.join(cikti_klasoru, webp_dosya)
    img.save(webp_yol, "WEBP", quality=VARSAYILAN_KALITE, method=6)

    # Srcset versiyonları (sadece yeterince geniş görseller için)
    srcset = None
    if gercek_genislik > SRCSET_MIN_GENISLIK:
        srcset = {}
        for boyut_adi, (maks_en, kalite) in SRCSET_BOYUTLARI.items():
            # Sadece orijinalden küçük versiyonlar üret
            if gercek_genislik > maks_en:
                oran = maks_en / img.width
                if oran < 1.0:
                    kucuk_img = img.resize(
                        (maks_en, int(img.height * oran)), resample
                    )
                else:
                    kucuk_img = img.copy()
                srcset_dosya = f"img_{uid}-{boyut_adi}.webp"
                srcset_yol = os.path.join(cikti_klasoru, srcset_dosya)
                kucuk_img.save(srcset_yol, "WEBP", quality=kalite, method=6)
                srcset[boyut_adi] = srcset_dosya

        if not srcset:
            srcset = None

    kazanilan = orijinal_boyut_kb - os.path.getsize(webp_yol) / 1024
    return OptimizasyonSonucu(
        webp=webp_dosya,
        original=orijinal_dosya,
        srcset=srcset,
        kazanilan_kb=round(kazanilan, 1),
        genislik=img.width,
        yukseklik=img.height,
    )


def toplu_optimize_et(klasor: str) -> list[dict]:
    """
    Klasördeki tüm JPG/JPEG/PNG görsellerini optimize eder.
    Zaten _original veya -sm/-md/-lg suffix'i olan dosyaları atlar.
    Döner: [{'dosya': ..., 'once_kb': ..., 'sonra_kb': ..., 'tasarruf_yuzde': ...}]
    """
    desteklenen = {".jpg", ".jpeg", ".png"}
    atla_ifadeleri = ("_original", "-sm.", "-md.", "-lg.")
    sonuclar = []

    dosyalar = sorted(os.listdir(klasor))
    for dosya_adi in dosyalar:
        uzanti = os.path.splitext(dosya_adi)[1].lower()
        if uzanti not in desteklenen:
            continue

        # Zaten işlenmiş dosyaları atla
        if any(ifade in dosya_adi for ifade in atla_ifadeleri):
            continue

        # Zaten aynı uid'den WebP var mı kontrol et (önceden işlenmiş)
        dosya_yolu = os.path.join(klasor, dosya_adi)
        once_kb = os.path.getsize(dosya_yolu) / 1024

        try:
            with open(dosya_yolu, "rb") as f:
                icerik = f.read()

            # Logo tespiti: dosya adında "logo" geçiyorsa logo modunda işle
            logo_mu = "logo" in dosya_adi.lower()

            # hp_ prefix'li dosyalar için özel uid üret (orijinal adı koru)
            isim_tabanı = os.path.splitext(dosya_adi)[0]
            sonuc = optimize_gorsel(
                icerik=icerik,
                orijinal_dosya_adi=dosya_adi,
                cikti_klasoru=klasor,
                logo_mu=logo_mu,
                uid=isim_tabanı,  # Orijinal ismi uid olarak kullan
            )

            sonra_kb = os.path.getsize(os.path.join(klasor, sonuc.webp)) / 1024
            tasarruf = ((once_kb - sonra_kb) / once_kb * 100) if once_kb > 0 else 0

            sonuclar.append({
                "dosya": dosya_adi,
                "webp": sonuc.webp,
                "srcset": sonuc.srcset,
                "once_kb": round(once_kb, 1),
                "sonra_kb": round(sonra_kb, 1),
                "tasarruf_yuzde": round(tasarruf, 1),
            })
            print(f"[optimize] {dosya_adi} -> {sonuc.webp} | {once_kb:.0f}KB -> {sonra_kb:.0f}KB (%{tasarruf:.0f} tasarruf)")

        except Exception as e:
            print(f"[optimize] HATA: {dosya_adi} -> {e}")
            sonuclar.append({
                "dosya": dosya_adi,
                "hata": str(e),
                "once_kb": round(once_kb, 1),
            })

    return sonuclar


if __name__ == "__main__":
    # Toplu optimizasyon: python -m app.image_optimizer
    import sys
    klasor = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static", "upload", "images"
    )
    print(f"Klasör: {klasor}")
    print("-" * 60)
    sonuclar = toplu_optimize_et(klasor)
    print("-" * 60)
    toplam_once = sum(s.get("once_kb", 0) for s in sonuclar)
    toplam_sonra = sum(s.get("sonra_kb", 0) for s in sonuclar if "sonra_kb" in s)
    print(f"Toplam: {toplam_once:.0f} KB → {toplam_sonra:.0f} KB")
    if toplam_once > 0:
        print(f"Genel tasarruf: %{(toplam_once - toplam_sonra) / toplam_once * 100:.0f}")

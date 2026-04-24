# -*- coding: utf-8 -*-
"""
Toplu görsel optimizasyonu sonrası DB URL güncelleme scripti.

Çalıştırma:
    # Docker ortamında (production):
    docker exec -it <app_container> python scripts/update_image_urls.py

    # Yerel geliştirme:
    source venv/Scripts/activate
    python scripts/update_image_urls.py

Ne yapar:
    1. site_settings tablosundaki logo URL'lerini WebP karşılıklarıyla günceller
    2. homepage_contents tablosundaki JSON içindeki hp_*.png URL'lerini WebP'ye çevirir
"""

import json
import os
import sys
import re

# Proje kökünü path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal
from app.models import SiteSettings, HomepageContent

IMAGES_STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "static", "upload", "images"
)

def webp_dosyasi_var_mi(url: str) -> tuple[bool, str]:
    """
    URL'ye karşılık gelen WebP dosyasının diskde olup olmadığını kontrol eder.
    Döner: (var_mi, webp_url)
    """
    if not url:
        return False, url

    dosya_adi = url.split("/")[-1]
    adi_tabanı = os.path.splitext(dosya_adi)[0]
    uzanti = os.path.splitext(dosya_adi)[1].lower()

    if uzanti == ".webp":
        return True, url

    # Batch optimizer tarafından üretilen adlandırma kuralı: img_{orijinal_ad}.webp
    webp_adi = f"img_{adi_tabanı}.webp"
    webp_yolu = os.path.join(IMAGES_STATIC_DIR, webp_adi)

    if os.path.exists(webp_yolu):
        webp_url = url.rsplit("/", 1)[0] + "/" + webp_adi
        return True, webp_url

    return False, url


def site_settings_guncelle(db) -> list[str]:
    """site_settings tablosundaki görsel URL'lerini WebP karşılıklarıyla günceller."""
    s = db.query(SiteSettings).first()
    if not s:
        return ["HATA: site_settings satırı bulunamadı"]

    guncellenen = []
    guncelleme_alanlari = [
        "logo_url", "logo_white_url", "favicon_url",
        "footer_bg_image_url", "default_og_image",
    ]

    for alan in guncelleme_alanlari:
        mevcut_url = getattr(s, alan, None)
        if not mevcut_url:
            continue

        uzanti = os.path.splitext(mevcut_url)[1].lower()
        if uzanti == ".webp":
            continue

        var_mi, yeni_url = webp_dosyasi_var_mi(mevcut_url)
        if var_mi and yeni_url != mevcut_url:
            setattr(s, alan, yeni_url)
            guncellenen.append(f"  {alan}: {mevcut_url} -> {yeni_url}")

    if guncellenen:
        db.flush()
        print("[site_settings] Guncellendi:")
        for g in guncellenen:
            print(g)
    else:
        print("[site_settings] Guncellenecek URL bulunamadi.")

    return guncellenen


def homepage_contents_guncelle(db) -> list[str]:
    """
    homepage_contents tablosundaki JSON data'sında hp_*.png URL'lerini WebP'ye çevirir.
    """
    kayitlar = db.query(HomepageContent).all()
    guncellenen = []

    for kayit in kayitlar:
        if not kayit.data:
            continue

        data = kayit.get_data() if hasattr(kayit, "get_data") else json.loads(kayit.data)
        data_str = json.dumps(data, ensure_ascii=False)
        yeni_data_str = data_str

        # hp_*.png ve diger png/jpg URL'leri bul
        pattern = r'/static/upload/images/([^"\']+\.(png|jpg|jpeg))'
        eslesmeler = re.findall(pattern, data_str)

        degistirilen = False
        for (eski_dosya, uzanti) in set(eslesmeler):
            eski_url = f"/static/upload/images/{eski_dosya}"
            var_mi, yeni_url = webp_dosyasi_var_mi(eski_url)
            if var_mi and yeni_url != eski_url:
                yeni_data_str = yeni_data_str.replace(eski_url, yeni_url)
                degistirilen = True
                guncellenen.append(f"  [{kayit.lang}] {eski_dosya} -> {yeni_url.split('/')[-1]}")

        if degistirilen:
            kayit.data = yeni_data_str
            db.flush()

    if guncellenen:
        print("[homepage_contents] Guncellendi:")
        for g in guncellenen:
            print(g)
    else:
        print("[homepage_contents] Guncellenecek URL bulunamadi.")

    return guncellenen


def main():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("Gorsel URL migrasyonu basliyor...")
        print("=" * 60)

        site_settings_guncelle(db)
        homepage_contents_guncelle(db)

        db.commit()
        print("\nTum guncellemeler basariyla kaydedildi.")
    except Exception as e:
        db.rollback()
        print(f"\nHATA: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

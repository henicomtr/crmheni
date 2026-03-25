#!/usr/bin/env python3
"""
HENİ CRM — SEO Kontrol Scripti
Tüm Jinja2 template dosyalarını tarar ve seo-report.md oluşturur.
"""

import os
import re
from pathlib import Path
from datetime import datetime

# ─── Ayarlar ────────────────────────────────────────────────────────────────

TEMPLATES_DIR = Path("templates")
OUTPUT_FILE = Path("seo-report.md")
DESTEKLENEN_DILLER = ["tr", "en", "de", "fr", "ar", "ru", "es"]

# Kontrol edilmeyecek dosyalar (partial'lar, base layout'lar hariç tutulabilir)
ATLA = {"base.html"}  # Base template'i ayrı değerlendir

# ─── Yardımcı Fonksiyonlar ───────────────────────────────────────────────────

def dosyalari_bul(dizin: Path) -> list[Path]:
    """Templates dizinindeki tüm .html dosyalarını bul."""
    return sorted(dizin.rglob("*.html"))


def metin_uzunlugu(html: str, tag_icerik: str) -> int:
    """Verilen string'in karakter uzunluğunu döndür."""
    return len(tag_icerik.strip())


def h_etiketlerini_bul(html: str) -> dict:
    """H1-H6 başlıklarını ve içeriklerini çıkar."""
    sonuc = {}
    for seviye in range(1, 7):
        pattern = rf"<h{seviye}[^>]*>(.*?)</h{seviye}>"
        eslesme = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
        # Jinja2 taglarını temizle
        temiz = [re.sub(r"\{[{%][^}%]*[}%]\}", "", e).strip() for e in eslesme]
        if temiz:
            sonuc[f"h{seviye}"] = temiz
    return sonuc


def img_etiketlerini_bul(html: str) -> list[dict]:
    """Tüm img taglarını ve alt değerlerini çıkar."""
    pattern = r"<img([^>]*)>"
    sonuclar = []
    for eslesen in re.finditer(pattern, html, re.IGNORECASE):
        attrs = eslesen.group(1)
        alt_eslesen = re.search(r'alt=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        src_eslesen = re.search(r'src=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        sonuclar.append({
            "src": src_eslesen.group(1) if src_eslesen else "",
            "alt": alt_eslesen.group(1) if alt_eslesen else None,
            "alt_var": alt_eslesen is not None,
            "alt_bos": (alt_eslesen.group(1).strip() == "") if alt_eslesen else True,
        })
    return sonuclar


def meta_bilgilerini_cek(html: str) -> dict:
    """Meta title, description, canonical ve lang bilgilerini çek."""
    bilgi = {}

    # Title
    title_eslesen = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title_eslesen:
        icerik = re.sub(r"\{[{%][^}%]*[}%]\}", "JINJA_VAR", title_eslesen.group(1)).strip()
        bilgi["title"] = icerik
        bilgi["title_uzunluk"] = len(icerik.replace("JINJA_VAR", ""))
    else:
        bilgi["title"] = None
        bilgi["title_uzunluk"] = 0

    # Meta description
    desc_eslesen = re.search(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE
    ) or re.search(
        r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']description["\']',
        html, re.IGNORECASE
    )
    if desc_eslesen:
        icerik = re.sub(r"\{[{%][^}%]*[}%]\}", "JINJA_VAR", desc_eslesen.group(1)).strip()
        bilgi["description"] = icerik
        bilgi["description_uzunluk"] = len(icerik.replace("JINJA_VAR", ""))
    else:
        bilgi["description"] = None
        bilgi["description_uzunluk"] = 0

    # Canonical
    bilgi["canonical"] = bool(re.search(r'rel=["\']canonical["\']', html, re.IGNORECASE))

    # Lang attribute
    lang_eslesen = re.search(r'<html[^>]*lang=["\']([^"\']*)["\']', html, re.IGNORECASE)
    bilgi["lang"] = lang_eslesen.group(1) if lang_eslesen else None

    # Hreflang
    hreflang_sayisi = len(re.findall(r'hreflang', html, re.IGNORECASE))
    bilgi["hreflang_sayisi"] = hreflang_sayisi

    return bilgi


def inline_css_sayisi(html: str) -> int:
    """Style attribute kullanım sayısını döndür."""
    return len(re.findall(r'\bstyle=["\']', html, re.IGNORECASE))


def bos_href_sayisi(html: str) -> int:
    """Boş veya # olan href sayısını döndür."""
    return len(re.findall(r'href=["\']#["\']|href=["\']["\']', html, re.IGNORECASE))


def kelime_sayisi(html: str) -> int:
    """HTML taglarını temizleyip yaklaşık kelime sayısını hesapla."""
    temiz = re.sub(r"<[^>]+>", " ", html)
    temiz = re.sub(r"\{[{%][^}%]*[}%]\}", " ", temiz)
    temiz = re.sub(r"\s+", " ", temiz).strip()
    return len(temiz.split())


# ─── Analiz Fonksiyonu ───────────────────────────────────────────────────────

def dosyayi_analiz_et(dosya_yolu: Path) -> dict:
    """Tek bir template dosyasını analiz et ve sonuç dict döndür."""
    try:
        html = dosya_yolu.read_text(encoding="utf-8")
    except Exception as e:
        return {"hata": str(e)}

    meta = meta_bilgilerini_cek(html)
    basliklar = h_etiketlerini_bul(html)
    gorseller = img_etiketlerini_bul(html)
    altsis_gorseller = [g for g in gorseller if not g["alt_var"] or g["alt_bos"]]

    # Hiyerarşi kontrolü
    h1_sayisi = len(basliklar.get("h1", []))
    hiyerarsi_hatasi = h1_sayisi != 1

    sonuc = {
        "dosya": str(dosya_yolu),
        "meta": meta,
        "h1_sayisi": h1_sayisi,
        "basliklar": basliklar,
        "hiyerarsi_hatasi": hiyerarsi_hatasi,
        "gorsel_sayisi": len(gorseller),
        "altsiz_gorsel_sayisi": len(altsis_gorseller),
        "altsiz_gorseller": altsis_gorseller[:5],  # İlk 5'ini raporla
        "inline_css_sayisi": inline_css_sayisi(html),
        "bos_href_sayisi": bos_href_sayisi(html),
        "yaklasik_kelime_sayisi": kelime_sayisi(html),
        "sorunlar": [],
        "uyarilar": [],
        "basarilar": [],
    }

    # ─── Kural Değerlendirmeleri ─────────────────────────────────────────────

    # Title
    if not meta["title"]:
        sonuc["sorunlar"].append("❌ `<title>` etiketi eksik")
    elif "JINJA_VAR" in meta["title"]:
        sonuc["basarilar"].append("✅ Title dinamik Jinja2 değişkeni içeriyor")
    elif meta["title_uzunluk"] < 30:
        sonuc["uyarilar"].append(f"⚠️ Title çok kısa ({meta['title_uzunluk']} karakter, önerilen: 50–60)")
    elif meta["title_uzunluk"] > 65:
        sonuc["uyarilar"].append(f"⚠️ Title çok uzun ({meta['title_uzunluk']} karakter, önerilen: 50–60)")
    else:
        sonuc["basarilar"].append(f"✅ Title uzunluğu uygun ({meta['title_uzunluk']} karakter)")

    # Description
    if not meta["description"]:
        sonuc["sorunlar"].append("❌ Meta description eksik")
    elif "JINJA_VAR" in meta["description"]:
        sonuc["basarilar"].append("✅ Description dinamik Jinja2 değişkeni içeriyor")
    elif meta["description_uzunluk"] < 100:
        sonuc["uyarilar"].append(f"⚠️ Description kısa ({meta['description_uzunluk']} karakter, önerilen: 150–160)")
    elif meta["description_uzunluk"] > 165:
        sonuc["uyarilar"].append(f"⚠️ Description uzun ({meta['description_uzunluk']} karakter, önerilen: 150–160)")
    else:
        sonuc["basarilar"].append(f"✅ Description uzunluğu uygun ({meta['description_uzunluk']} karakter)")

    # H1
    if h1_sayisi == 0:
        sonuc["sorunlar"].append("❌ Sayfada H1 etiketi yok")
    elif h1_sayisi > 1:
        sonuc["sorunlar"].append(f"❌ Birden fazla H1 var ({h1_sayisi} adet)")
    else:
        sonuc["basarilar"].append("✅ Tek H1 mevcut")

    # Görseller
    if altsis_gorseller:
        sonuc["sorunlar"].append(f"❌ {len(altsis_gorseller)} görselde alt text eksik/boş")
    elif gorseller:
        sonuc["basarilar"].append(f"✅ Tüm görsellerde alt text var ({len(gorseller)} görsel)")

    # Canonical
    if not meta["canonical"]:
        sonuc["uyarilar"].append("⚠️ Canonical URL etiketi eksik")
    else:
        sonuc["basarilar"].append("✅ Canonical etiketi mevcut")

    # Lang
    if not meta["lang"]:
        sonuc["uyarilar"].append("⚠️ `<html lang='...'>` attribute eksik")
    else:
        sonuc["basarilar"].append(f"✅ Lang attribute var: `{meta['lang']}`")

    # Hreflang
    if meta["hreflang_sayisi"] == 0:
        sonuc["uyarilar"].append("⚠️ Hreflang etiketleri eksik (7 dil için gerekli)")
    elif meta["hreflang_sayisi"] < len(DESTEKLENEN_DILLER):
        sonuc["uyarilar"].append(f"⚠️ Hreflang eksik: {meta['hreflang_sayisi']}/{len(DESTEKLENEN_DILLER)} dil tanımlanmış")
    else:
        sonuc["basarilar"].append(f"✅ Hreflang tüm diller için tanımlanmış")

    # Inline CSS
    if sonuc["inline_css_sayisi"] > 20:
        sonuc["uyarilar"].append(f"⚠️ Yüksek inline CSS kullanımı ({sonuc['inline_css_sayisi']} adet)")

    # Boş href
    if sonuc["bos_href_sayisi"] > 0:
        sonuc["uyarilar"].append(f"⚠️ {sonuc['bos_href_sayisi']} adet boş/# href tespit edildi")

    # Kelime sayısı (sadece içerik sayfaları için)
    if "partial" not in str(dosya_yolu) and "base" not in str(dosya_yolu).lower():
        if sonuc["yaklasik_kelime_sayisi"] < 150:
            sonuc["uyarilar"].append(f"⚠️ Az içerik: yaklaşık {sonuc['yaklasik_kelime_sayisi']} kelime (önerilen: 300+)")

    return sonuc


# ─── Rapor Oluşturucu ────────────────────────────────────────────────────────

def puan_hesapla(sonuc: dict) -> str:
    """Basit bir skor döndür: 🟢 İyi / 🟡 Orta / 🔴 Kritik"""
    kritik = len(sonuc.get("sorunlar", []))
    uyari = len(sonuc.get("uyarilar", []))
    if kritik > 0:
        return "🔴"
    elif uyari > 2:
        return "🟡"
    return "🟢"


def rapor_olustur(analizler: list[dict]) -> str:
    """Tüm analizleri birleştirip Markdown rapor döndür."""
    tarih = datetime.now().strftime("%d.%m.%Y %H:%M")
    toplam = len(analizler)
    kritik_dosyalar = [a for a in analizler if a.get("sorunlar")]
    temiz_dosyalar = [a for a in analizler if not a.get("sorunlar") and not a.get("uyarilar")]

    satirlar = [
        f"# 🔍 SEO Kontrol Raporu",
        f"",
        f"**Tarih:** {tarih}  ",
        f"**Kontrol Eden:** Claude Code SEO Ajanı  ",
        f"**Taranan Dosya:** {toplam}  ",
        f"**Kritik Sorun İçeren:** {len(kritik_dosyalar)}  ",
        f"**Temiz Dosya:** {len(temiz_dosyalar)}  ",
        f"",
        f"---",
        f"",
        f"## 📊 Özet Puan Tablosu",
        f"",
        f"| Durum | Dosya | Sorun | Uyarı | Başarı |",
        f"|---|---|---|---|---|",
    ]

    for a in analizler:
        if "hata" in a:
            continue
        puan = puan_hesapla(a)
        dosya_kisa = a["dosya"].replace("templates/", "").replace("templates\\", "")
        satirlar.append(
            f"| {puan} | `{dosya_kisa}` | "
            f"{len(a['sorunlar'])} | "
            f"{len(a['uyarilar'])} | "
            f"{len(a['basarilar'])} |"
        )

    # Kritik sorunlar
    satirlar += ["", "---", "", "## ❌ Kritik Sorunlar (Hemen Düzelt)", ""]
    kritik_var = False
    for a in analizler:
        if a.get("sorunlar"):
            kritik_var = True
            dosya_kisa = a["dosya"].replace("templates/", "").replace("templates\\", "")
            satirlar.append(f"### `{dosya_kisa}`")
            for s in a["sorunlar"]:
                satirlar.append(f"- {s}")
            satirlar.append("")
    if not kritik_var:
        satirlar.append("_Kritik sorun bulunamadı. 🎉_\n")

    # Uyarılar
    satirlar += ["---", "", "## ⚠️ Uyarılar (Bu Hafta Düzelt)", ""]
    uyari_var = False
    for a in analizler:
        if a.get("uyarilar"):
            uyari_var = True
            dosya_kisa = a["dosya"].replace("templates/", "").replace("templates\\", "")
            satirlar.append(f"### `{dosya_kisa}`")
            for u in a["uyarilar"]:
                satirlar.append(f"- {u}")
            satirlar.append("")
    if not uyari_var:
        satirlar.append("_Uyarı bulunamadı._\n")

    # İyi giden kısımlar (özet)
    satirlar += ["---", "", "## ✅ İyi Giden Kısımlar", ""]
    for a in analizler:
        if a.get("basarilar"):
            dosya_kisa = a["dosya"].replace("templates/", "").replace("templates\\", "")
            satirlar.append(f"**`{dosya_kisa}`:** {', '.join(a['basarilar'][:2])}")
    satirlar.append("")

    satirlar += [
        "---",
        "",
        "## 📝 Sonraki Adım",
        "",
        "> Bu rapor Claude Code SEO Ajanı tarafından oluşturuldu.",
        "> Kritik sorunları düzeltmek için Claude Code'da `/seo-kontrol` komutunu çalıştır",
        "> ve hangi sayfadan başlamak istediğini belirt.",
        "",
    ]

    return "\n".join(satirlar)


# ─── Ana Akış ────────────────────────────────────────────────────────────────

def main():
    if not TEMPLATES_DIR.exists():
        print(f"HATA: '{TEMPLATES_DIR}' dizini bulunamadı. Proje kök dizininde çalıştır.")
        return

    dosyalar = dosyalari_bul(TEMPLATES_DIR)
    if not dosyalar:
        print("Hiç HTML dosyası bulunamadı.")
        return

    print(f"🔍 {len(dosyalar)} template dosyası taranıyor...\n")

    analizler = []
    for dosya in dosyalar:
        print(f"  → {dosya}")
        analiz = dosyayi_analiz_et(dosya)
        analizler.append(analiz)

    rapor = rapor_olustur(analizler)
    OUTPUT_FILE.write_text(rapor, encoding="utf-8")

    # Özet terminale yazdır
    toplam_sorun = sum(len(a.get("sorunlar", [])) for a in analizler)
    toplam_uyari = sum(len(a.get("uyarilar", [])) for a in analizler)
    print(f"\n✅ Tarama tamamlandı!")
    print(f"   📄 Rapor: {OUTPUT_FILE}")
    print(f"   ❌ Kritik sorun: {toplam_sorun}")
    print(f"   ⚠️  Uyarı: {toplam_uyari}")
    print(f"\nClaude Code'da '/seo-kontrol' komutunu çalıştırarak detaylı analiz ve düzeltme önerilerini alabilirsin.")


if __name__ == "__main__":
    main()
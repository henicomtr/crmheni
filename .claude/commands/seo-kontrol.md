    # SEO Kontrol Ajanı

Bu komutu çalıştırdığında aşağıdaki adımları sırayla uygula.

---

## Adım 1 — Python Scriptini Çalıştır

```bash
python agents/seo_checker.py
```

Script `seo-report.md` dosyasını oluşturacak. Bunu bekle.

---

## Adım 2 — Raporu Oku ve Analiz Et

Oluşan `seo-report.md` dosyasını oku. Her sayfayı şu kriterlere göre değerlendir:

### Meta Kontrolleri
- `<title>` var mı? Uzunluğu 50–60 karakter arasında mı?
- `<meta name="description">` var mı? Uzunluğu 150–160 karakter arasında mı?
- `<meta name="keywords">` var mı? (opsiyonel ama kontrol et)
- `<link rel="canonical">` var mı?
- `lang` attribute doğru mu? (ör: TR sayfası için `lang="tr"`)

### Başlık Hiyerarşisi
- Sayfada yalnızca 1 adet `<h1>` var mı?
- `<h2>`, `<h3>` sırası mantıklı mı? (h1→h2→h3, atlama var mı?)
- `<h1>` içinde hedef anahtar kelime geçiyor mu?

### İçerik Kalitesi
- İlk `<p>` paragrafında hedef anahtar kelime var mı?
- Sayfada yeterli metin içeriği var mı? (minimum 300 kelime — ürün/kategori sayfaları için)
- Metin/görsel oranı dengeli mi? (Sadece görsel, metin yok sayfalar işaretle)

### Görseller
- Tüm `<img>` taglarında `alt` attribute var mı?
- `alt` değerleri boş mu, anlamlı mı?
- Görsel dosya isimleri anlamlı mı? (ör: `guzellik-urun.jpg` vs `IMG_001.jpg`)

### Teknik SEO
- `<html lang="...">` doğru dil kodu ile mi başlıyor?
- Sayfada `<script>` tagları `<body>` sonuna taşınmış mı?
- Inline CSS aşırı kullanılmış mı? (performans etkisi)
- Broken link şüphesi var mı? (href="#" veya boş href)

### Çok Dilli Kontrol (HENİ CRM özelinde)
- `hreflang` tag'leri var mı? (7 dil için: tr, en, de, fr, ar, ru, es)
- Her dil versiyonu için ayrı meta title/description var mı?
- URL yapısı dil prefix'i içeriyor mu? (`/tr/`, `/en/` vb.)

---

## Adım 3 — Raporu Güncelle

`seo-report.md` dosyasına şu formatta sonuçları yaz:

```markdown
# SEO Kontrol Raporu
**Tarih:** {tarih}
**Kontrol Eden:** Claude Code SEO Ajanı

---

## Özet Puan Tablosu

| Sayfa / Template | Meta | Başlıklar | İçerik | Görseller | Teknik | Çok Dilli | Toplam |
|---|---|---|---|---|---|---|---|
| base.html | ✅ | ✅ | ⚠️ | ❌ | ✅ | ⚠️ | 3/5 |

**Lejant:** ✅ Tamam | ⚠️ Dikkat | ❌ Kritik Sorun

---

## Kritik Sorunlar (Hemen Düzelt)
> ❌ listesi buraya

## Uyarılar (Bu Hafta Düzelt)
> ⚠️ listesi buraya

## İyi Giden Kısımlar
> ✅ listesi buraya

---

## Düzeltme Önerileri

### 1. {sorun başlığı}
**Dosya:** `templates/...`
**Sorun:** ...
**Çözüm:**
\```html
{düzeltilmiş kod örneği}
\```
```

---

## Adım 4 — Düzeltme Onayı İste

Raporu sunduktan sonra sor:

> "Kritik sorunları şimdi düzeltmemi ister misin? Hangi sayfadan başlayalım?"

Onay almadan hiçbir template dosyasını değiştirme.
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Bu dosya, Claude Code'un bu repoda çalışırken uyması gereken kuralları ve proje rehberini içerir.

---

## Projeyi Çalıştırma

```bash
# Sanal ortamı etkinleştir
source venv/Scripts/activate  # Windows (bash)

# Geliştirme sunucusunu başlat
uvicorn app.main:app --reload

# Belirli host/port ile çalıştır
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Bu projede henüz build adımı, linting konfigürasyonu veya test altyapısı yoktur.

---

## Proje Özeti

**HENİ CRM**, güzellik ve temizlik ürünleri sektörüne yönelik çok dilli B2B e-ticaret/CRM platformudur.
**Stack:** FastAPI + SQLAlchemy + Jinja2 + SQLite (→ PostgreSQL geçişi planlanıyor)
**Geliştirici:** Tek kişi (solo proje)
**Desteklenen Diller:** EN, TR, DE, FR, AR, RU, ES

---

## Mimari Genel Bakış

### Modül Düzeni

**Route dosyaları:**
- `app/routes_admin.py` — Admin panel route'ları (~93KB, JWT ile korumalı, izin sistemi var)
- `app/routes_showroom.py` — Müşterilere açık public showroom route'ları (~72KB)
- `app/routes_pricing.py` — İç fiyatlandırma motoru (`/esk/pricing/*`); `pricing` izni gerektirir
- `app/routes_feeds.py` — Google Merchant Center XML feed endpoint'leri (her dil için ayrı)
- `app/routes_push.py` — Web Push / VAPID push notification endpoint'leri
- `app/routes_webhook.py` — Webhook endpoint'leri

**Servis katmanı (`app/services/`):**
- `currency_service.py` — TCMB XML feed, 1 saatlik cache, fallback kurlar; `LANG_CURRENCY`, `convert()`, `get_rates()` export eder
- `pricing_service.py` — 3 aşamalı iç maliyet hesaplama (hammadde → yarı mamul → nihai ürün); tüm maliyetler USD cinsinden

**Yardımcı modüller:**
- `app/main.py` — FastAPI başlatma, tüm router'ları bağlama, DB tablo oluşturma + kolon migrasyonu, varsayılan veri seed
- `app/models.py` — Tüm SQLAlchemy ORM modelleri
- `app/auth.py` — JWT token oluşturma/doğrulama, bcrypt şifre hash
- `app/config.py` — Ürün kategorileri (`CATEGORIES`), konteyner sabitleri (`PALLETS_PER_20FT=13`, `PALLETS_PER_40FT=24`), `SECRET_KEY`; `.env` ile yapılandırılır
- `app/lang.py` — Dil tespiti ve URL yönlendirme (şu an devre dışı — bkz. aşağıdaki not)
- `app/image_optimizer.py` — PIL tabanlı görsel optimizasyon; WebP dönüşümü + srcset (sm/md/lg) üretimi
- `app/database.py` — SQLAlchemy engine, `SessionLocal`, `Base`

**Şablonlar:**
- `templates/` — Jinja2 HTML şablonları
- `templates/partials/` — `site_header.html`, `site_footer.html`, `media_picker_modal.html`
- `templates/base.html` — Public sayfa temel şablonu
- `templates/admin_layout.html` — Admin panel temel şablonu

### Çok Dilli Sistem

`LangMiddleware` şu an **devre dışı**; dil rotaları `routes_showroom.py` içinde manuel tanımlıdır:
- `/` → EN, `/tr` → TR, `/de` → DE, `/fr` → FR
- Ürün detay: `/product/{slug}` (EN), `/tr/urun/{slug}` (TR), `/de/produkt/{slug}` (DE), `/fr/produit/{slug}` (FR)

Dil tespiti: URL prefix → cookie → Accept-Language header → varsayılan EN.
Döviz eşlemesi: EN→USD, TR→TRY, DE/FR/RU/ES/AR→EUR.

### Veritabanı

SQLite (`heni.db`). Tablolar startup'ta `Base.metadata.create_all()` ile oluşturulur.
Kolon migrasyonları `main.py` içinde `inspect(engine)` ile mevcut kolonlar kontrol edilerek ham `ALTER TABLE` ile yapılır.

**⚠️ Önemli:** PostgreSQL'e geçiş planlanmaktadır. Yeni yazılan kodlar bu geçişe uyumlu olmalıdır:
- SQLite'a özgü sözdizimi (`PRAGMA`, `AUTOINCREMENT`) kullanma.
- Genel SQLAlchemy ORM pattern'larına sadık kal.

**Ana tablolar:**
- `products`, `product_translations` — çok dilli ürünler; palet bazlı indirim kademeleri (1–5+ palet)
- `customers`, `suppliers` — iş bağlantıları
- `quote_requests`, `request_messages`, `request_attachments` — B2B talep formu + konuşma geçmişi
- `finance`, `account_transactions` — finans ve cari hesap takibi
- `pages`, `page_translations`, `faq_items` — CMS (generic + landing page şablonları)
- `category_contents`, `category_translations`, `category_faqs` — kategori bazlı CMS
- `homepage_contents` — JSON tabanlı anasayfa editör blokları
- `site_settings` — tekil satır; logo, sosyal linkler, analitik kodu, özel CSS, sertifika logoları
- **Fiyatlandırma motoru:** `stock_items`, `pricing_products`, `formula_items`, `finished_products`, `packaging_items`, `pricing_results`
- `push_subscriptions` — Web Push VAPID abone kayıtları
- `product_ratings` — tarayıcı başına bir kez oy (browser_id ile deduplicate)
- `service_page_contents` — hizmet sayfaları için JSON içerik blokları

### Kimlik Doğrulama ve İzin Sistemi

JWT tabanlı admin kimlik doğrulama. Token'lar HTTP-only cookie'de saklanır.
`User.is_superadmin=True` olan kullanıcı her şeye erişir. Diğer kullanıcılar `User.permissions` (JSON liste) ile kontrol edilir.
İzin anahtarları: `urunler`, `musteriler`, `talepler`, `finans`, `pricing`, `ayarlar`, vb.
Varsayılan admin bilgileri, kullanıcı yoksa `main.py` içinde seed edilir.

### Temel Pattern'lar

- Her route dosyası DB erişimi için `db: Session = Depends(get_db)` alır.
- Admin route'ları her handler başında JWT cookie doğrular ve `user.has_permission(...)` ile izin kontrol eder.
- Ürün fiyatlandırması 5 palet-miktar kademesi kullanır (1, 2, 3, 4, 5+ palet); `Product.calculate_discounted_price(pallets)` metodu kullanılır.
- `Product.get_translation(lang)` ve `Product.get_slug_for(lang)` EN fallback'i otomatik uygular — tüm dil erişimleri bu metodlar üzerinden yapılmalıdır.
- `HomepageContent` satırları esnek anasayfa bölümü düzenleme için JSON blob saklar.
- `SiteSettings` her zaman `.first()` ile çekilen tek satırdır.
- Görsel upload'larında `image_optimizer.py` çağrılır; `static/upload/` altına WebP + srcset versiyonları yazılır.
- Push notification'lar `routes_push.py` üzerinden; ENV değişkenleri: `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIMS_EMAIL`.

---

## ⚙️ Çalışma Kuralları (ZORUNLU)

### 1. Önce Plan, Sonra Kod
Her görevde önce şunları açıkla:
- Ne yapacaksın?
- Hangi dosyaları değiştireceksin?
- Beklenmedik yan etki var mı?

Onay almadan kod yazmaya başlama.

### 2. Yorum Satırları Türkçe Olsun
Tüm kod yorumları (`#` ve docstring'ler) Türkçe yazılmalıdır.

```python
# ✅ Doğru
def get_product(db: Session, product_id: int):
    # Ürünü ID'ye göre veritabanından çek
    return db.query(Product).filter(Product.id == product_id).first()
```

### 3. Büyük Değişikliklerde Test Zorunlu
10+ satır etkileyen değişiklikler için önce test senaryosu yaz veya manuel test adımlarını belirt.

### 4. Kodlama Stili
- **snake_case** kullan: değişkenler, fonksiyonlar, dosya isimleri
- **Fonksiyon isimleri fiil ile başlasın:** `get_`, `create_`, `update_`, `delete_`, `check_`, `send_`
- Kısaltmadan kaçın: `usr` değil `user`, `prod` değil `product`

---

## 🚫 Yasak Davranışlar

- SQLite'a özgü sözdizimi ekleme (PostgreSQL geçişine hazırlık)
- Onay almadan birden fazla dosyayı aynı anda değiştirme
- Mevcut migration'ları (`main.py` içindeki `ALTER TABLE` blokları) silme veya değiştirme
- `SECRET_KEY` veya JWT logic'ini refactor etme

---

## 🤖 Ajanlar

### SEO Kontrol Ajanı
**Komut:** `/seo-kontrol`
**Script:** `agents/seo_checker.py`
**Çıktı:** `seo-report.md`

Ne kontrol eder:
- Meta title ve description (varlık + karakter uzunluğu)
- H1–H6 başlık hiyerarşisi
- Tüm görsellerde alt text varlığı
- Canonical URL ve hreflang (7 dil için)
- Inline CSS aşırı kullanımı ve boş href tespiti
- Yaklaşık içerik kelime sayısı

**Kullanım:**
```bash
# 1. Önce scripti çalıştır (terminal):
python agents/seo_checker.py

# 2. Sonra Claude Code'da:
/seo-kontrol
```

Claude raporu okuyup kritik sorunları öncelikli sıraya koyar ve onayınla düzeltir.

---

## 📁 Slash Komutları

| Komut | Amaç |
|---|---|
| `/yeni-route` | Yeni endpoint eklemek için adım adım rehber |
| `/yeni-model` | Yeni veritabanı modeli eklemek için şablon |
| `/seo-kontrol` | Tüm template'leri SEO kriterleriyle tara ve raporla |

# CLAUDE.md

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
**Stack:** FastAPI + SQLAlchemy + Jinja2 + SQLite (PostgreSQL geçişi planlanmaktadır)
**Geliştirici:** Tek kişi (solo proje)
**Desteklenen Diller:** EN, TR, DE, FR, AR, RU, ES

---

## Mimari Genel Bakış

### Modül Düzeni

- `app/main.py` — FastAPI uygulama başlatma, middleware, DB tablo oluşturma/migrasyon, varsayılan veri seed
- `app/models.py` — Tüm SQLAlchemy ORM modelleri
- `app/routes_admin.py` — Admin panel route'ları (93KB, JWT ile korumalı)
- `app/routes_showroom.py` — Müşterilere açık public route'lar (72KB)
- `app/routes_webhook.py` — Webhook endpoint'leri
- `app/auth.py` — JWT token oluşturma/doğrulama, bcrypt şifre hash
- `app/config.py` — Ürün kategorileri, palet sabitleri (20ft=13, 40ft=24 palet)
- `app/lang.py` — Dil tespiti ve URL yönlendirme
- `app/currency_service.py` — TCMB XML feed, 1 saatlik cache, fallback kurlar
- `app/database.py` — SQLAlchemy engine, `SessionLocal`, `Base`
- `templates/` — Jinja2 HTML şablonları; `templates/partials/` ortak parçalar
- `static/upload/` — Kullanıcı yüklü görsel, video ve belgeler

### Çok Dilli Sistem

Dil URL prefix'i ile belirlenir (`/tr/`, `/de/`) → cookie → Accept-Language header → varsayılan EN.
Dile özel URL slug'ları mevcuttur (ör: `/product/{slug}` EN, `/tr/urun/{slug}` TR).
Döviz eşlemesi: EN→USD, TR→TRY, DE/FR/RU/ES→EUR.

### Veritabanı

SQLite (`heni.db`). Tablolar startup'ta `Base.metadata.create_all()` ile oluşturulur.
Kolon migrasyonları `main.py` içinde ham `ALTER TABLE` ile yapılır (migration aracı yoktur).

**⚠️ Önemli:** PostgreSQL'e geçiş planlanmaktadır. Yeni yazılan kodlar bu geçişe uyumlu olmalıdır:
- SQLite'a özgü sözdizimi (ör: `PRAGMA`, `AUTOINCREMENT`) kullanma.
- Genel SQLAlchemy ORM pattern'larına sadık kal.

**Ana tablolar:**
- `products`, `product_translations` — çok dilli ürünler, palet fiyatlandırma kademeleri
- `customers`, `suppliers` — iş bağlantıları
- `quote_requests` — B2B lead formu
- `finance`, `account_transactions` — finans takibi
- `pages`, `page_translations`, `faq_items` — CMS
- `category_contents`, `category_translations`, `category_faqs` — kategori bazlı CMS
- `homepage_contents` — JSON tabanlı anasayfa editör blokları
- `site_settings` — logo, sosyal bağlantılar, analitik kodu, özel CSS için tekil satır

### Kimlik Doğrulama

JWT tabanlı admin kimlik doğrulama. Token'lar HTTP-only cookie'de saklanır.
Varsayılan admin bilgileri, kullanıcı yoksa `main.py` içinde seed edilir.
JWT secret `app/config.py` içindedir (`SECRET_KEY`).

### Temel Pattern'lar

- Her route dosyası DB erişimi için `db: Session = Depends(get_db)` alır.
- Admin route'ları her handler başında JWT cookie doğrular.
- Ürün fiyatlandırması 5 palet-miktar kademesi kullanır (1, 2, 3, 4, 5+ palet).
- `HomepageContent` satırları esnek anasayfa bölümü düzenleme için JSON blob saklar.
- `SiteSettings` her zaman `.first()` ile çekilen tek satırdır.

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